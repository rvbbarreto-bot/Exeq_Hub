"""U19 — denegada tipada · outbox idempotente · cancel_orphan."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.outbox import EVENT_AUTHORIZED, publish_nfe_lifecycle_event
from apps.nfe.polling import poll_nfe_invoice
from apps.nfe.reconciliation import reconcile_stale_nfe_batch
from apps.ops.models import OutboxMessage
from integrations.sefaz_nfe.port import NfeEmitResult, StubNfeProvider


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_RECONCILE_STALE_SECONDS = 60
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
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
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av T",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_outbox_lifecycle_idempotent(nfe_settings, tenant_a, provider_sp, customer_b2b):
    inv = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.AUTHORIZED,
        series=1,
        number=1,
        number_consumed=True,
        tp_amb="2",
        total_cents=100,
        access_key="35260837229907000137550010000000011000000010",
        issue_date=timezone.localdate(),
    )
    a = publish_nfe_lifecycle_event(inv, event_type=EVENT_AUTHORIZED)
    b = publish_nfe_lifecycle_event(inv, event_type=EVENT_AUTHORIZED)
    assert a is not None
    assert b is None
    assert (
        OutboxMessage.objects.filter(
            tenant=tenant_a, event_type=EVENT_AUTHORIZED, aggregate_id=inv.id
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_poll_denegada_marks_flag(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.POLLING,
        series=1,
        number=2,
        number_consumed=True,
        tp_amb="2",
        total_cents=100,
        access_key="35260837229907000137550010000000011000000011",
        fiscal_snapshot={"sefaz": {"n_rec": "1", "poll_attempts": 0}},
        issue_date=timezone.localdate(),
    )

    class DenegProvider:
        kind = "mock"

        def consultar(self, **kwargs):
            return NfeEmitResult(
                status="denegada",
                access_key=kwargs.get("access_key") or "",
                rejection_code="110",
                rejection_message="Uso Denegado",
                raw={"denegada": True, "cStat": "110"},
            )

    with patch("apps.nfe.polling.get_nfe_provider", return_value=DenegProvider()):
        result = poll_nfe_invoice(inv)

    assert result.status == NfeInvoice.Status.REJECTED
    assert result.rejection_code == "110"
    assert (result.last_validation or {}).get("denegada") is True
    assert OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.rejected", aggregate_id=inv.id
    ).exists()


@pytest.mark.django_db
def test_reconcile_cancel_orphan(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.CANCEL_REQUESTED,
        series=1,
        number=3,
        number_consumed=True,
        tp_amb="2",
        total_cents=100,
        access_key="35260837229907000137550010000000011000000012",
        issue_date=timezone.localdate(),
    )
    NfeInvoice.objects.filter(pk=inv.pk).update(
        updated_at=timezone.now() - timedelta(seconds=300)
    )
    stats = reconcile_stale_nfe_batch(limit=20)
    inv.refresh_from_db()
    assert stats["cancel_restored"] == 1
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert inv.rejection_code == "CANCEL_ORPHAN"
