"""Reconciliação NFC-e stale."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.tenant_emission import apply_emission_flags
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfce.reconciliation import (
    _recover_submitting,
    invoices_stale_polling,
    reconcile_stale_nfce_batch,
)


@pytest.fixture
def nfce_ctx(settings, tenant_a):
    settings.NFCE_ENABLED = True
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings"])
    provider = Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Reconcile Lab",
        tax_regime=TaxRegime.SIMPLES,
        address={"uf": "SP", "codigo_ibge": "3504107", "logradouro": "Rua A"},
        is_active=True,
    )
    return tenant_a, provider


@pytest.mark.django_db
def test_stale_polling_detected(nfce_ctx):
    tenant_a, provider = nfce_ctx
    inv = NfceInvoice.objects.create(
        tenant=tenant_a,
        provider=provider,
        idempotency_key="rec-poll",
        issue_date=timezone.localdate(),
        status=NfceInvoice.Status.POLLING,
    )
    NfceInvoice.objects.filter(pk=inv.pk).update(
        updated_at=timezone.now() - timedelta(minutes=10)
    )
    stale = invoices_stale_polling(limit=10)
    assert inv.id in {i.id for i in stale}


@pytest.mark.django_db
def test_recover_submitting_with_key_to_polling(nfce_ctx):
    tenant_a, provider = nfce_ctx
    inv = NfceInvoice.objects.create(
        tenant=tenant_a,
        provider=provider,
        idempotency_key="rec-sub",
        issue_date=timezone.localdate(),
        status=NfceInvoice.Status.SUBMITTING,
        access_key="35260837229907000137650010000000011000000010",
        number=1,
    )
    assert _recover_submitting(inv) == "polling"
    inv.refresh_from_db()
    assert inv.status == NfceInvoice.Status.POLLING


@pytest.mark.django_db
def test_recover_submitting_without_key_fails(nfce_ctx):
    tenant_a, provider = nfce_ctx
    inv = NfceInvoice.objects.create(
        tenant=tenant_a,
        provider=provider,
        idempotency_key="rec-orphan",
        issue_date=timezone.localdate(),
        status=NfceInvoice.Status.SUBMITTING,
        number=2,
    )
    assert _recover_submitting(inv) == "failed"
    inv.refresh_from_db()
    assert inv.rejection_code == "SUBMIT_ORPHAN"


@pytest.mark.django_db
def test_reconcile_batch_schedules_poll(nfce_ctx):
    tenant_a, provider = nfce_ctx
    inv = NfceInvoice.objects.create(
        tenant=tenant_a,
        provider=provider,
        idempotency_key="rec-batch",
        issue_date=timezone.localdate(),
        status=NfceInvoice.Status.POLLING,
    )
    NfceInvoice.objects.filter(pk=inv.pk).update(
        updated_at=timezone.now() - timedelta(minutes=10)
    )
    with patch("apps.nfce.polling.schedule_nfce_poll") as sched:
        stats = reconcile_stale_nfce_batch(limit=10)
    assert stats["polling_scheduled"] >= 1
    sched.assert_called()
