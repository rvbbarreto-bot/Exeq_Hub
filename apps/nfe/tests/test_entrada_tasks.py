"""Celery tasks e beat tick — NF-e entrada."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.models import NfeDistribuicaoCursor, NfeEntradaDocument
from apps.nfe.entrada.tasks import distribuicao_sync_task, distribuicao_tick_task
from apps.nfe.entrada.tick import list_distribuicao_due_cursors, run_distribuicao_tick


@pytest.fixture
def entrada_settings(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )


@pytest.mark.django_db
def test_sync_task_creates_documents(entrada_settings, tenant_a, provider_sp):
    result = distribuicao_sync_task(str(tenant_a.id), str(provider_sp.id))
    assert result["ok"] is True
    assert result["documents_created"] == 2
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 2


@pytest.mark.django_db
def test_tick_enqueues_due_cursor(entrada_settings, tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.automatic_enabled = True
    cursor.interval_seconds = 3600
    cursor.last_query_at = timezone.now() - timedelta(hours=2)
    cursor.save()

    due = list_distribuicao_due_cursors(limit=10)
    assert len(due) == 1

    with patch("apps.nfe.entrada.tasks.distribuicao_sync_task.delay") as delay_mock:
        stats = run_distribuicao_tick(limit=10)
    assert stats["enqueued"] == 1
    delay_mock.assert_called_once()


@pytest.mark.django_db
def test_tick_skips_recent_query(entrada_settings, tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.automatic_enabled = True
    cursor.interval_seconds = 3600
    cursor.last_query_at = timezone.now()
    cursor.save()

    assert list_distribuicao_due_cursors(limit=10) == []


@pytest.mark.django_db
def test_tick_skips_automatic_disabled(entrada_settings, tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.automatic_enabled = False
    cursor.last_query_at = timezone.now() - timedelta(hours=5)
    cursor.save()

    assert list_distribuicao_due_cursors(limit=10) == []


@pytest.mark.django_db
def test_tick_task_runs(entrada_settings, tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.automatic_enabled = True
    cursor.last_query_at = timezone.now() - timedelta(hours=2)
    cursor.save()

    result = distribuicao_tick_task(limit=10)
    assert result["enqueued"] == 1
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 2


@pytest.mark.django_db
def test_tick_skips_blocked_cursor(entrada_settings, tenant_a, provider_sp):
    from django.utils import timezone

    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.automatic_enabled = True
    cursor.blocked_until = timezone.now() + timezone.timedelta(hours=2)
    cursor.last_query_at = timezone.now() - timezone.timedelta(hours=5)
    cursor.save()
    assert list_distribuicao_due_cursors(limit=10) == []


@pytest.mark.django_db
def test_tick_global_disabled(settings, tenant_a, provider_sp):
    settings.NFE_ENTRADA_ENABLED = False
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.automatic_enabled = True
    cursor.save()
    assert list_distribuicao_due_cursors(limit=10) == []


@pytest.mark.django_db
def test_sync_task_not_found_returns_ok_false(db):
    result = distribuicao_sync_task(
        "00000000-0000-0000-0000-000000000099",
        "00000000-0000-0000-0000-000000000088",
    )
    assert result["ok"] is False
    assert result["reason"] == "not_found"


@pytest.mark.django_db
def test_sync_skipped_when_nsu_changed_mid_flight(entrada_settings, tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)

    original_fetch = __import__(
        "apps.nfe.entrada.services.distribuicao",
        fromlist=["_fetch_dist_batches"],
    )._fetch_dist_batches

    def _fetch_and_mutate(**kwargs):
        NfeDistribuicaoCursor.objects.filter(pk=cursor.pk).update(ult_nsu="000000000000099")
        return original_fetch(**kwargs)

    with patch(
        "apps.nfe.entrada.services.distribuicao._fetch_dist_batches",
        side_effect=_fetch_and_mutate,
    ):
        from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once

        result = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")

    assert result.skipped is True
