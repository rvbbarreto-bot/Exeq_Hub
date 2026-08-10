"""DoD domínio #4 — NumberSeries sem colisão em concorrência (D-06)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from django.db import connection, connections

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.models import NfeNumberSeries
from apps.nfe.numbering import reserve_next_number


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
        tax_regime=TaxRegime.SIMPLES,
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
        is_active=True,
    )


@pytest.mark.django_db
def test_sequential_reserve_is_strictly_increasing(tenant_a, provider_sp):
    nums = [
        reserve_next_number(
            tenant_id=tenant_a.id,
            provider_id=provider_sp.id,
            series=1,
            tp_amb="2",
        )
        for _ in range(15)
    ]
    assert nums == list(range(1, 16))
    row = NfeNumberSeries.objects.get(
        tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2"
    )
    assert row.next_number == 16


@pytest.mark.django_db(transaction=True)
def test_concurrent_reserves_unique_numbers(tenant_a, provider_sp):
    """
    Vários workers reservam ao mesmo tempo — nNF únicos e contíguos.

    transaction=True permite threads com conexão própria (pytest-django).
    """
    # Série pré-existente: contende só no incremento (caminho crítico do emit)
    NfeNumberSeries.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        series=1,
        tp_amb="2",
        next_number=1,
        is_active=True,
    )

    n_workers = 12
    barrier = threading.Barrier(n_workers, timeout=30)
    tid = tenant_a.id
    pid = provider_sp.id

    def worker() -> int:
        connection.close()
        barrier.wait()
        try:
            return reserve_next_number(
                tenant_id=tid,
                provider_id=pid,
                series=1,
                tp_amb="2",
            )
        finally:
            connections.close_all()

    numbers: list[int] = []
    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(worker) for _ in range(n_workers)]
        for fut in as_completed(futures):
            try:
                numbers.append(fut.result())
            except BaseException as exc:  # noqa: BLE001 — capturar deadlock/lock sqlite
                errors.append(exc)

    # Aceita falhas raras de lock em SQLite se o conjunto válido for sem duplicata;
    # em Postgres/lab saudável espera-se zero erros.
    assert not errors, f"falhas na reserva concorrente: {errors!r}"
    assert len(numbers) == n_workers
    assert len(set(numbers)) == n_workers, f"colisão: {sorted(numbers)}"
    assert sorted(numbers) == list(range(1, n_workers + 1))

    row = NfeNumberSeries.objects.get(
        tenant_id=tid, provider_id=pid, series=1, tp_amb="2"
    )
    assert row.next_number == n_workers + 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_create_race(tenant_a, provider_sp):
    """Create da série sob corrida (sem seed) — IntegrityError tratável."""
    n_workers = 8
    barrier = threading.Barrier(n_workers, timeout=30)
    tid = tenant_a.id
    pid = provider_sp.id
    assert not NfeNumberSeries.objects.filter(
        tenant_id=tid, provider_id=pid, series=9, tp_amb="2"
    ).exists()

    def worker() -> int:
        connection.close()
        barrier.wait()
        try:
            return reserve_next_number(
                tenant_id=tid,
                provider_id=pid,
                series=9,
                tp_amb="2",
            )
        finally:
            connections.close_all()

    numbers: list[int] = []
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        for fut in as_completed([pool.submit(worker) for _ in range(n_workers)]):
            numbers.append(fut.result())

    assert len(set(numbers)) == n_workers
    assert sorted(numbers) == list(range(1, n_workers + 1))
    assert (
        NfeNumberSeries.objects.filter(
            tenant_id=tid, provider_id=pid, series=9, tp_amb="2"
        ).count()
        == 1
    )
