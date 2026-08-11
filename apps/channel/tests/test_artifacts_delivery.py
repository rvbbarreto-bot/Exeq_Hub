"""Fase 2 — entrega PDF/XML via WhatsApp (WA-ART)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification, ChannelSession
from apps.channel.services import MediaDeliveryError, deliver_nf_artifacts
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfArtifact, NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage
from shared.storage import get_storage

PHONE = "+5511999990000"


@pytest.fixture
def authorized_issue(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Consultoria",
        codigo_tributacao_nacional_iss="010101",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)

    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="wa-art-1",
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=150000,
    )
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED
    return issue


@pytest.mark.django_db
def test_wa_art_01_deliver_pdf_and_xml(tenant_a, authorized_issue):
    session = ChannelSession.objects.create(
        tenant=tenant_a,
        idempotency_key=f"{PHONE}:art1",
        phone_e164=PHONE,
        status=ChannelSession.Status.EMITTED,
        nf_issue=authorized_issue,
        draft_payload={},
    )
    notes = deliver_nf_artifacts(
        tenant=tenant_a,
        nf_issue=authorized_issue,
        phone_e164=PHONE,
        session=session,
    )
    event_types = {n.event_type for n in notes}
    assert "nf_issue.authorized" in event_types
    assert "nf_issue.authorized.pdf" in event_types
    assert "nf_issue.authorized.xml" in event_types
    assert all(n.status == ChannelNotification.Status.SENT for n in notes)
    assert all(n.provider == "evolution" for n in notes)

    pdf_note = next(n for n in notes if n.event_type.endswith(".pdf"))
    assert "DANFSe_" in pdf_note.message_body or "DANFSe" in pdf_note.message_body


@pytest.mark.django_db
def test_wa_art_02_media_bytes_match_storage(tenant_a, authorized_issue):
    """WA-ART-02 — bytes enviados idênticos ao StoredFile."""
    pdf = NfArtifact.objects.get(nf_issue=authorized_issue, kind=NfArtifact.Kind.PDF)
    stored_bytes = get_storage().get(key=pdf.stored_file.object_key)
    captured = {}

    class CapturingGateway:
        def send_text(self, **kwargs):
            return {"ok": True, "ref": "t", "provider": "evolution"}

        def send_media(self, *, phone_e164, filename, mime_type, data, caption=""):
            captured[filename] = data
            return {"ok": True, "ref": "m", "provider": "evolution", "filename": filename}

    with patch(
        "apps.channel.services.get_whatsapp_gateway", return_value=CapturingGateway()
    ):
        deliver_nf_artifacts(
            tenant=tenant_a, nf_issue=authorized_issue, phone_e164=PHONE
        )

    pdf_name = next(k for k in captured if k.endswith(".pdf"))
    assert captured[pdf_name] == stored_bytes


@pytest.mark.django_db
def test_wa_art_03_media_failure_outbox_retries(tenant_a, authorized_issue):
    """WA-ART-03 — falha de mídia falha o outbox; nota permanece authorized."""
    ChannelSession.objects.create(
        tenant=tenant_a,
        idempotency_key=f"{PHONE}:art3",
        phone_e164=PHONE,
        status=ChannelSession.Status.EMITTED,
        nf_issue=authorized_issue,
        draft_payload={},
    )
    msg = OutboxMessage.objects.filter(
        tenant=tenant_a,
        event_type="nf_issue.authorized",
        aggregate_id=authorized_issue.id,
    ).first()
    if msg is None:
        msg = OutboxMessage.objects.create(
            tenant=tenant_a,
            event_type="nf_issue.authorized",
            aggregate_type="nf_issue",
            aggregate_id=authorized_issue.id,
            payload={"focus_ref": authorized_issue.focus_ref},
            available_at=timezone.now(),
        )
    else:
        msg.status = OutboxMessage.Status.PENDING
        msg.attempts = 0
        msg.available_at = timezone.now()
        msg.save(update_fields=["status", "attempts", "available_at", "updated_at"])

    class FailMediaGateway:
        def send_text(self, **kwargs):
            return {"ok": True, "ref": "t", "provider": "evolution"}

        def send_media(self, **kwargs):
            return {"ok": False, "error": "Evolution down", "provider": "evolution"}

    with patch(
        "apps.channel.services.get_whatsapp_gateway", return_value=FailMediaGateway()
    ):
        result = claim_and_dispatch(str(msg.id))

    assert result == "failed"
    msg.refresh_from_db()
    assert msg.status == OutboxMessage.Status.FAILED
    authorized_issue.refresh_from_db()
    assert authorized_issue.status == NfIssue.Status.AUTHORIZED


@pytest.mark.django_db
def test_wa_art_04_retry_skips_already_sent(tenant_a, authorized_issue):
    """WA-ART-04 — retry não reenvia o que já foi SENT."""
    calls = {"text": 0, "media": 0}

    class FlakyGateway:
        def send_text(self, **kwargs):
            calls["text"] += 1
            return {"ok": True, "ref": f"t{calls['text']}", "provider": "evolution"}

        def send_media(self, **kwargs):
            calls["media"] += 1
            if calls["media"] == 1:
                return {"ok": False, "error": "fail pdf", "provider": "evolution"}
            return {"ok": True, "ref": f"m{calls['media']}", "provider": "evolution"}

    with patch(
        "apps.channel.services.get_whatsapp_gateway", return_value=FlakyGateway()
    ):
        with pytest.raises(MediaDeliveryError):
            deliver_nf_artifacts(
                tenant=tenant_a, nf_issue=authorized_issue, phone_e164=PHONE
            )
        deliver_nf_artifacts(
            tenant=tenant_a, nf_issue=authorized_issue, phone_e164=PHONE
        )

    # texto 1× (segunda chamada pula); media 3× (pdf fail + pdf ok + xml ok)
    assert calls["text"] == 1
    assert calls["media"] == 3
    sent = ChannelNotification.objects.filter(
        tenant=tenant_a, nf_issue=authorized_issue, status=ChannelNotification.Status.SENT
    )
    assert sent.filter(event_type="nf_issue.authorized").count() == 1
    assert sent.filter(event_type="nf_issue.authorized.pdf").count() == 1
    assert sent.filter(event_type="nf_issue.authorized.xml").count() == 1


@pytest.mark.django_db
def test_wa_art_05_resend_on_demand(tenant_a, authorized_issue):
    """WA-ART-05 — reenvio sob demanda gera novas notificações após limpar SENT."""
    deliver_nf_artifacts(tenant=tenant_a, nf_issue=authorized_issue, phone_e164=PHONE)
    first_count = ChannelNotification.objects.filter(
        tenant=tenant_a, nf_issue=authorized_issue, status=ChannelNotification.Status.SENT
    ).count()
    assert first_count >= 3

    # Reenvio explícito: apaga marcadores SENT do tipo artefato (simula ação Admin)
    ChannelNotification.objects.filter(
        tenant=tenant_a,
        nf_issue=authorized_issue,
        event_type__in=[
            "nf_issue.authorized",
            "nf_issue.authorized.pdf",
            "nf_issue.authorized.xml",
        ],
    ).update(status=ChannelNotification.Status.FAILED)

    notes = deliver_nf_artifacts(
        tenant=tenant_a, nf_issue=authorized_issue, phone_e164=PHONE
    )
    assert len(notes) >= 3
    authorized_issue.refresh_from_db()
    assert authorized_issue.status == NfIssue.Status.AUTHORIZED


@pytest.mark.django_db
def test_wa_art_06_meta_provider_records_media(tenant_a, authorized_issue):
    tenant_a.settings = {"whatsapp_provider": "meta"}
    tenant_a.save(update_fields=["settings"])
    notes = deliver_nf_artifacts(
        tenant=tenant_a, nf_issue=authorized_issue, phone_e164=PHONE
    )
    media = [n for n in notes if n.event_type.endswith((".pdf", ".xml"))]
    assert media
    assert all(n.provider == "meta" for n in media)
    assert all(n.status == ChannelNotification.Status.SENT for n in media)


@pytest.mark.django_db
def test_outbox_authorized_delivers_to_session_phone(tenant_a, authorized_issue):
    ChannelSession.objects.create(
        tenant=tenant_a,
        idempotency_key=f"{PHONE}:outbox",
        phone_e164=PHONE,
        status=ChannelSession.Status.EMITTED,
        nf_issue=authorized_issue,
        draft_payload={},
    )
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nf_issue.authorized",
        aggregate_type="nf_issue",
        aggregate_id=authorized_issue.id,
        payload={"focus_ref": authorized_issue.focus_ref},
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    assert ChannelNotification.objects.filter(
        tenant=tenant_a,
        phone_e164=PHONE,
        event_type="nf_issue.authorized.pdf",
        status=ChannelNotification.Status.SENT,
    ).exists()
