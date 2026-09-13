"""Fase 1 canal WhatsApp — casos WA-FLX do roteiro QA."""

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.utils import timezone

from apps.channel.engine import (
    MSG_GREETING,
    MSG_INVALID_AMOUNT,
    MSG_INVALID_DOCUMENT,
    MSG_UNAUTHORIZED,
    process_inbound,
)
from apps.channel.models import ChannelSession
from apps.channel.tasks import expire_stale_sessions
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.master_data.models import Customer, TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service

PHONE = "+5511999990000"
_ids = count(1)


def _send(tenant, text, phone=PHONE):
    return process_inbound(
        tenant=tenant,
        phone_e164=phone,
        message_id=f"m{next(_ids)}",
        text=text,
    )


@pytest.fixture
def channel_setup(tenant_a):
    tenant_a.settings = {"whatsapp_authorized_phones": [PHONE]}
    tenant_a.save(update_fields=["settings"])
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
        name="Cliente Existente",
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
    return {"provider": provider, "customer": customer, "service": service}


def _drive_to_confirm(tenant, document="529.982.247-25", amount="1.500,00"):
    _send(tenant, "quero emitir nota")
    _send(tenant, document)
    _send(tenant, "1")
    session, reply = _send(tenant, amount)
    return session, reply


@pytest.mark.django_db
def test_wa_flx_01_happy_path_emits(tenant_a, channel_setup):
    session, greeting = _send(tenant_a, "quero emitir nota")
    assert greeting == MSG_GREETING
    assert session.status == ChannelSession.Status.COLLECTING

    _, menu = _send(tenant_a, "529.982.247-25")
    assert "Consultoria" in menu

    _, ask_amount = _send(tenant_a, "1")
    assert "valor" in ask_amount.lower()

    session, summary = _send(tenant_a, "1.500,00")
    assert session.status == ChannelSession.Status.READY_TO_CONFIRM
    assert "R$ 1.500,00" in summary
    # WA-FLX-05: ISS aparece calculado no resumo, nunca foi perguntado
    assert "ISS estimado: R$ 30,00" in summary

    session, done = _send(tenant_a, "CONFIRMAR")
    assert session.status == ChannelSession.Status.EMITTED
    issue = NfIssue.objects.get(tenant=tenant_a)
    assert issue.status == NfIssue.Status.AUTHORIZED
    assert issue.amount_cents == 150000
    assert session.nf_issue_id == issue.id
    assert "Ref:" in done


@pytest.mark.django_db
def test_wa_flx_02_invalid_document_reprompts(tenant_a, channel_setup):
    _send(tenant_a, "oi")
    session, reply = _send(tenant_a, "12345")
    assert reply == MSG_INVALID_DOCUMENT
    assert session.status == ChannelSession.Status.COLLECTING
    assert Customer.objects.filter(tenant=tenant_a).count() == 1  # só o do fixture


@pytest.mark.django_db
def test_wa_flx_03_missing_data_loops_on_amount(tenant_a, channel_setup):
    _send(tenant_a, "oi")
    _send(tenant_a, "529.982.247-25")
    _send(tenant_a, "1")
    _, reply = _send(tenant_a, "abc")
    assert reply == MSG_INVALID_AMOUNT
    session, summary = _send(tenant_a, "100,00")
    assert session.status == ChannelSession.Status.READY_TO_CONFIRM


@pytest.mark.django_db
def test_wa_flx_04_cancel_at_confirm(tenant_a, channel_setup):
    _drive_to_confirm(tenant_a)
    session, reply = _send(tenant_a, "CANCELAR")
    assert session.status == ChannelSession.Status.CANCELLED
    assert NfIssue.objects.filter(tenant=tenant_a).count() == 0
    assert "cancelada" in reply.lower()


@pytest.mark.django_db
def test_wa_flx_06_confirm_twice_single_issue(tenant_a, channel_setup):
    _drive_to_confirm(tenant_a)
    _send(tenant_a, "CONFIRMAR")
    session, reply = _send(tenant_a, "CONFIRMAR")
    assert NfIssue.objects.filter(tenant=tenant_a).count() == 1
    assert "já foi emitida" in reply


@pytest.mark.django_db
def test_wa_flx_07_stale_session_expires(tenant_a, channel_setup):
    session, _ = _send(tenant_a, "oi")
    ChannelSession.objects.filter(pk=session.pk).update(
        last_message_at=timezone.now() - timedelta(minutes=45)
    )
    expired = expire_stale_sessions()
    assert expired == 1

    new_session, reply = _send(tenant_a, "oi de novo")
    assert new_session.pk != session.pk
    assert reply == MSG_GREETING


@pytest.mark.django_db
def test_wa_flx_07_inline_expiration_on_new_message(tenant_a, channel_setup):
    session, _ = _send(tenant_a, "oi")
    ChannelSession.objects.filter(pk=session.pk).update(
        last_message_at=timezone.now() - timedelta(minutes=45)
    )
    new_session, reply = _send(tenant_a, "oi")
    session.refresh_from_db()
    assert session.status == ChannelSession.Status.EXPIRED
    assert new_session.pk != session.pk


@pytest.mark.django_db
def test_wa_flx_08_unauthorized_phone_blocked(tenant_a, channel_setup):
    session, reply = _send(tenant_a, "quero nota", phone="+5511000000000")
    assert session is None
    assert reply == MSG_UNAUTHORIZED
    assert ChannelSession.objects.filter(tenant=tenant_a).count() == 0


@pytest.mark.django_db
def test_wa_flx_09_new_customer_get_or_create(tenant_a, channel_setup):
    _send(tenant_a, "oi")
    _, ask_name = _send(tenant_a, "111.444.777-35")
    assert "nome" in ask_name.lower()
    _, menu = _send(tenant_a, "Novo Tomador Ltda")
    assert "Consultoria" in menu
    created = Customer.objects.get(tenant=tenant_a, document="11144477735")
    assert created.name == "Novo Tomador Ltda"
    assert created.document_type == "cpf"


@pytest.mark.django_db
def test_wa_flx_10_rejected_emission_not_emitted(tenant_a, channel_setup, settings):
    settings.NFSE_CONVENIO_DENY_IBGE = "3504107"
    _drive_to_confirm(tenant_a)
    session, reply = _send(tenant_a, "CONFIRMAR")
    assert session.status != ChannelSession.Status.EMITTED
    assert "recusada" in reply.lower()
    issue = NfIssue.objects.get(tenant=tenant_a)
    assert issue.status == NfIssue.Status.REJECTED


@pytest.mark.django_db
def test_duplicate_message_id_no_double_processing(tenant_a, channel_setup):
    process_inbound(
        tenant=tenant_a, phone_e164=PHONE, message_id="dup-1", text="oi"
    )
    session, reply = process_inbound(
        tenant=tenant_a, phone_e164=PHONE, message_id="dup-1", text="oi"
    )
    assert reply == ""
    assert ChannelSession.objects.filter(tenant=tenant_a).count() == 1


_WH_TOKEN = {"HTTP_X_EXEQ_WEBHOOK_TOKEN": "test-webhook-token"}


@pytest.mark.django_db
def test_webhook_flow_replies_and_audits(api_client, tenant_a, channel_setup):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        {
            "tenant_slug": "acme",
            "phone_e164": PHONE,
            "message_id": "wh-1",
            "text": "quero emitir",
        },
        format="json",
        **_WH_TOKEN,
    )
    assert response.status_code == 200
    assert response.data["status"] == "collecting"
    assert response.data["reply"] == MSG_GREETING
    from apps.channel.models import ChannelNotification

    note = ChannelNotification.objects.get(tenant=tenant_a, event_type="channel.reply")
    assert note.status == "sent"


@pytest.mark.django_db
def test_webhook_unauthorized_blocked(api_client, tenant_a, channel_setup):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        {
            "tenant_slug": "acme",
            "phone_e164": "+5511000000000",
            "message_id": "wh-2",
            "text": "quero emitir",
        },
        format="json",
        **_WH_TOKEN,
    )
    assert response.status_code == 200
    assert response.data["status"] == "blocked"
    assert response.data["reply"] == MSG_UNAUTHORIZED
    assert ChannelSession.objects.filter(tenant=tenant_a).count() == 0
