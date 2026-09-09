"""EX-EMT-03/04 — concorrência emissão iFood (B5)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest
from django.db import connection, connections

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_order_nfce
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfe.services import create_product


@pytest.fixture
def nfce_settings(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings", "updated_at"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ FOOD LAB",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )


@pytest.fixture
def ready_order(tenant_a, nfce_settings, provider_sp):
    nfe = create_product(
        tenant=tenant_a,
        code="CC-01",
        description="Item CC",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="CC-SKU",
        name="Prato CC",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("20"),
    )
    food.nfe_product = nfe
    food.save(update_fields=["nfe_product"])
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="CC-ORDER",
        customer_name="Cliente CC",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


@pytest.mark.django_db
def test_ex_emt_03_sequential_double_emit(tenant_a, ready_order):
    """EX-EMT-03: duplo clique sequencial — idempotência garante uma NFC-e."""
    first = emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="u1")
    second = emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="u2")
    assert first["status"] == "authorized"
    assert second["status"] == "skipped"
    assert second["reason"] == "already_authorized"
    ready_order.refresh_from_db()
    assert (
        NfceInvoice.objects.filter(
            tenant=tenant_a,
            idempotency_key=f"food:ifood:{ready_order.id}",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor == "sqlite",
    reason="SQLite não suporta select_for_update concorrente de forma confiável",
)
def test_ex_emt_03_concurrent_emit(tenant_a, ready_order):
    """EX-EMT-03: emissões paralelas — lock + idempotência."""
    n_workers = 6
    barrier = threading.Barrier(n_workers, timeout=30)
    oid = ready_order.id

    def worker():
        connection.close()
        barrier.wait()
        try:
            return emit_food_order_nfce(tenant=tenant_a, order_id=oid, actor="cc-test")
        finally:
            connections.close_all()

    results = []
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(worker) for _ in range(n_workers)]
        for fut in as_completed(futures):
            results.append(fut.result())

    assert sum(1 for r in results if r.get("status") == "authorized") == 1
    ready_order.refresh_from_db()
    assert ready_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert (
        NfceInvoice.objects.filter(
            tenant=tenant_a,
            idempotency_key=f"food:ifood:{ready_order.id}",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor == "sqlite",
    reason="SQLite não suporta select_for_update concorrente de forma confiável",
)
def test_ex_emt_04_two_operators_same_order(tenant_a, ready_order):
    """EX-EMT-04: dois operadores em paralelo — uma emissão vence."""
    n_workers = 4
    barrier = threading.Barrier(n_workers, timeout=30)
    oid = ready_order.id

    def operator(session: str):
        connection.close()
        barrier.wait()
        try:
            return emit_food_order_nfce(
                tenant=tenant_a,
                order_id=oid,
                actor=f"operator:{session}",
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(operator, f"s{i}") for i in range(n_workers)]
        results = [f.result() for f in as_completed(futures)]

    assert sum(1 for r in results if r.get("status") == "authorized") == 1
    assert (
        NfceInvoice.objects.filter(
            tenant=tenant_a,
            idempotency_key=f"food:ifood:{ready_order.id}",
        ).count()
        == 1
    )
