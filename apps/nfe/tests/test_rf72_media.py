"""RF-72 — entrega DANFE/XML via WhatsApp em nfe.authorized (paridade WA-ART)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification, ChannelSession
from apps.channel.services import MediaDeliveryError, deliver_nfe_artifacts
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeArtifact, NfeInvoice
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage
from shared.storage import get_storage

PHONE = "+5511999887766"
OPS = "+5511888776655"


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
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


@pytest.fixture
def authorized_nfe(nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="RF72",
        description="Item RF72",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key=f"rf72-{product.id}",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert NfeArtifact.objects.filter(invoice=inv).exists()
    return inv


def _link_session(tenant, inv, phone=PHONE):
    return ChannelSession.objects.create(
        tenant=tenant,
        idempotency_key=f"{phone}:rf72:{inv.id}",
        phone_e164=phone,
        status=ChannelSession.Status.EMITTED,
        nfe_invoice=inv,
        draft_payload={},
    )


@pytest.mark.django_db
def test_rf72_deliver_danfe_and_xml(tenant_a, authorized_nfe):
    session = _link_session(tenant_a, authorized_nfe)
    notes = deliver_nfe_artifacts(
        tenant=tenant_a,
        nfe_invoice=authorized_nfe,
        phone_e164=PHONE,
        session=session,
    )
    types = {n.event_type for n in notes}
    assert "nfe.authorized" in types
    assert "nfe.authorized.pdf" in types
    assert "nfe.authorized.xml" in types
    assert all(n.status == ChannelNotification.Status.SENT for n in notes)
    assert all(n.nfe_invoice_id == authorized_nfe.id for n in notes)
    pdf_note = next(n for n in notes if n.event_type.endswith(".pdf"))
    assert "DANFE" in pdf_note.message_body


@pytest.mark.django_db
def test_rf72_media_bytes_match_storage(tenant_a, authorized_nfe):
    pdf = NfeArtifact.objects.get(
        invoice=authorized_nfe, kind=NfeArtifact.Kind.DANFE_PDF
    )
    stored = get_storage().get(key=pdf.stored_file.object_key)
    captured: dict[str, bytes] = {}

    class Cap:
        def send_text(self, **kwargs):
            return {"ok": True, "ref": "t", "provider": "evolution"}

        def send_media(self, *, phone_e164, filename, mime_type, data, caption=""):
            captured[filename] = data
            return {"ok": True, "ref": "m", "provider": "evolution"}

    with patch("apps.channel.services.get_whatsapp_gateway", return_value=Cap()):
        deliver_nfe_artifacts(
            tenant=tenant_a, nfe_invoice=authorized_nfe, phone_e164=PHONE
        )
    name = next(k for k in captured if k.endswith(".pdf"))
    assert captured[name] == stored


@pytest.mark.django_db
def test_rf72_outbox_session_delivers_media(tenant_a, authorized_nfe):
    _link_session(tenant_a, authorized_nfe)
    tenant_a.settings = {"notify_phone": OPS}
    tenant_a.save(update_fields=["settings"])

    msg = OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.authorized", aggregate_id=authorized_nfe.id
    ).first()
    assert msg is not None
    msg.status = OutboxMessage.Status.PENDING
    msg.attempts = 0
    msg.available_at = timezone.now()
    msg.save(update_fields=["status", "attempts", "available_at", "updated_at"])

    assert claim_and_dispatch(str(msg.id)) == "processed"
    assert ChannelNotification.objects.filter(
        tenant=tenant_a,
        phone_e164=PHONE,
        event_type="nfe.authorized.pdf",
        status=ChannelNotification.Status.SENT,
    ).exists()
    assert ChannelNotification.objects.filter(
        tenant=tenant_a,
        phone_e164=PHONE,
        event_type="nfe.authorized.xml",
        status=ChannelNotification.Status.SENT,
    ).exists()
    # Ops (diferente do solicitante) recebe só texto
    ops = ChannelNotification.objects.filter(
        tenant=tenant_a, phone_e164=OPS, event_type="nfe.authorized"
    )
    assert ops.count() == 1
    assert not ChannelNotification.objects.filter(
        tenant=tenant_a, phone_e164=OPS, event_type__endswith=".pdf"
    ).exists()


@pytest.mark.django_db
def test_rf72_without_session_ops_text_only_no_media(tenant_a, authorized_nfe):
    tenant_a.settings = {"notify_phone": OPS}
    tenant_a.save(update_fields=["settings"])
    msg = OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.authorized", aggregate_id=authorized_nfe.id
    ).first()
    msg.status = OutboxMessage.Status.PENDING
    msg.attempts = 0
    msg.available_at = timezone.now()
    msg.save(update_fields=["status", "attempts", "available_at", "updated_at"])

    assert claim_and_dispatch(str(msg.id)) == "processed"
    assert ChannelNotification.objects.filter(
        tenant=tenant_a, phone_e164=OPS, event_type="nfe.authorized"
    ).exists()
    assert not ChannelNotification.objects.filter(
        tenant=tenant_a, event_type="nfe.authorized.pdf"
    ).exists()


@pytest.mark.django_db
def test_rf72_media_failure_fails_outbox(tenant_a, authorized_nfe):
    _link_session(tenant_a, authorized_nfe)
    msg = OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.authorized", aggregate_id=authorized_nfe.id
    ).first()
    msg.status = OutboxMessage.Status.PENDING
    msg.attempts = 0
    msg.available_at = timezone.now()
    msg.save(update_fields=["status", "attempts", "available_at", "updated_at"])

    class FailMedia:
        def send_text(self, **kwargs):
            return {"ok": True, "ref": "t", "provider": "evolution"}

        def send_media(self, **kwargs):
            return {"ok": False, "error": "down", "provider": "evolution"}

    with patch(
        "apps.channel.services.get_whatsapp_gateway", return_value=FailMedia()
    ):
        assert claim_and_dispatch(str(msg.id)) == "failed"
    msg.refresh_from_db()
    assert msg.status == OutboxMessage.Status.FAILED
    authorized_nfe.refresh_from_db()
    assert authorized_nfe.status == NfeInvoice.Status.AUTHORIZED


@pytest.mark.django_db
def test_rf72_retry_skips_already_sent(tenant_a, authorized_nfe):
    calls = {"text": 0, "media": 0}

    class Flaky:
        def send_text(self, **kwargs):
            calls["text"] += 1
            return {"ok": True, "ref": f"t{calls['text']}", "provider": "evolution"}

        def send_media(self, **kwargs):
            calls["media"] += 1
            if calls["media"] == 1:
                return {"ok": False, "error": "fail pdf", "provider": "evolution"}
            return {"ok": True, "ref": f"m{calls['media']}", "provider": "evolution"}

    with patch("apps.channel.services.get_whatsapp_gateway", return_value=Flaky()):
        with pytest.raises(MediaDeliveryError):
            deliver_nfe_artifacts(
                tenant=tenant_a, nfe_invoice=authorized_nfe, phone_e164=PHONE
            )
        deliver_nfe_artifacts(
            tenant=tenant_a, nfe_invoice=authorized_nfe, phone_e164=PHONE
        )

    assert calls["text"] == 1
    assert calls["media"] == 3
    sent = ChannelNotification.objects.filter(
        tenant=tenant_a,
        nfe_invoice=authorized_nfe,
        status=ChannelNotification.Status.SENT,
    )
    assert sent.filter(event_type="nfe.authorized").count() == 1
    assert sent.filter(event_type="nfe.authorized.pdf").count() == 1
    assert sent.filter(event_type="nfe.authorized.xml").count() == 1
