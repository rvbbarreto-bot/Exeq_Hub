"""U17 — RF-64 DANFE retry · RF-92 poll_exhausted · RF-91 metrics."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.artifacts import has_danfe_pdf, has_xml_authorized
from apps.nfe.metrics import compute_nfe_ops_metrics
from apps.nfe.models import NfeInvoice
from apps.nfe.pdf_retry import retry_pending_danfe_batch, retry_pending_danfe_for_invoice
from apps.nfe.polling import poll_nfe_invoice
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage
from integrations.sefaz_nfe.port import StubNfeProvider


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    settings.NFE_POLL_MAX_ATTEMPTS = 2
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


def _emit_authorized(tenant, provider, customer, key: str):
    product = create_product(
        tenant=tenant,
        code=f"U17-{key[:6]}",
        description="Item U17",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key=f"u17-{key}",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    emit_invoice(inv)
    inv.refresh_from_db()
    return inv


def _seed_polling(tenant, provider, customer, number: int = 9) -> NfeInvoice:
    return NfeInvoice.objects.create(
        tenant=tenant,
        provider=provider,
        customer=customer,
        status=NfeInvoice.Status.POLLING,
        series=1,
        number=number,
        number_consumed=True,
        tp_amb="2",
        total_cents=1000,
        access_key="35260837229907000137550010000000019000000019",
        fiscal_snapshot={
            "sefaz": {"n_rec": "123456789012345", "poll_attempts": 2},
            "emitente": {"cnpj": "37229907000137"},
        },
        issue_date=timezone.localdate(),
    )


@pytest.mark.django_db
def test_poll_exhausted_enqueues_outbox(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _seed_polling(tenant_a, provider_sp, customer_b2b)
    with patch("apps.nfe.polling.get_nfe_provider", return_value=StubNfeProvider()):
        result = poll_nfe_invoice(inv)

    assert result.status == NfeInvoice.Status.FAILED
    assert result.rejection_code == "POLL_EXHAUSTED"
    msg = OutboxMessage.objects.get(
        tenant=tenant_a, event_type="nfe.poll_exhausted", aggregate_id=inv.id
    )
    assert msg.payload.get("reason") == "poll_exhausted"
    assert msg.payload.get("max_attempts") == 2


@pytest.mark.django_db
def test_dispatcher_poll_exhausted_notifies(tenant_a):
    tenant_a.settings = {"notify_phone": "+5511888888888"}
    tenant_a.save(update_fields=["settings"])
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nfe.poll_exhausted",
        aggregate_type="nfe_invoice",
        aggregate_id=tenant_a.id,
        payload={
            "number": 9,
            "series": 1,
            "poll_attempts": 3,
            "max_attempts": 2,
            "access_key": "35260837229907000137550010000000019000000019",
        },
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    note = ChannelNotification.objects.get(
        tenant=tenant_a, event_type="nfe.poll_exhausted"
    )
    assert "poll esgotado" in note.message_body.lower()


@pytest.mark.django_db
def test_pdf_retry_recovers_danfe(
    nfe_settings, tenant_a, provider_sp, customer_b2b, monkeypatch
):
    calls = {"n": 0}

    def _boom_then_ok(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("render fail once")
        return b"%PDF-1.4 retry-ok\n%%EOF\n"

    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render.render_danfe_pdf",
        _boom_then_ok,
    )
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_danfe_pdf",
        _boom_then_ok,
    )
    inv = _emit_authorized(tenant_a, provider_sp, customer_b2b, "pdf-retry")
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert has_xml_authorized(inv)
    assert not has_danfe_pdf(inv)
    assert (inv.last_validation or {}).get("pdf_pending") is True

    ok = retry_pending_danfe_for_invoice(inv)
    inv.refresh_from_db()
    assert ok is True
    assert has_danfe_pdf(inv)
    assert not (inv.last_validation or {}).get("pdf_pending")

    stats = retry_pending_danfe_batch(limit=10)
    assert stats["scanned"] >= 0


@pytest.mark.django_db
def test_metrics_compute_and_api(
    nfe_settings, tenant_a, provider_sp, customer_b2b, api_client, auth_header
):
    inv = _emit_authorized(tenant_a, provider_sp, customer_b2b, "metrics")
    assert inv.status == NfeInvoice.Status.AUTHORIZED

    m = compute_nfe_ops_metrics(tenant=tenant_a, days=30)
    assert m["total"] >= 1
    assert m["by_status"].get(NfeInvoice.Status.AUTHORIZED, 0) >= 1
    assert m["authorize_rate"] is not None
    assert m["authorize_rate"] >= 0

    r = api_client.get("/api/v1/nfe/metrics/?days=30", **auth_header)
    assert r.status_code == 200
    assert r.data["days"] == 30
    assert r.data["total"] >= 1
