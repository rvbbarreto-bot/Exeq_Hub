"""ADR-DAS-DELIVERY-001 — testes de entrega DAS/DARF ao contador."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.certificates import upload_a1_certificate
from apps.channel.models import ChannelNotification
from apps.das.delivery import (
    DasEmailDeliveryError,
    deliver_guia_email,
    deliver_guia_to_accountant,
    handle_guia_delivery_outbox,
    resolve_accountant_email,
)
from apps.das.models import GuiaFiscal
from apps.das.services import emitir_guia
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage


def _pfx(days=60):
    from datetime import datetime, timedelta, timezone as tz

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption,
        pkcs12,
    )
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EXEQ Test")])
    now = datetime.now(tz.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(b"secret"),
    )


@pytest.fixture
def provider(tenant_a):
    return create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador DAS",
        tax_regime=TaxRegime.SIMPLES,
    )


@pytest.fixture
def cert_a1(tenant_a, provider, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    return upload_a1_certificate(
        tenant=tenant_a,
        label="A1 DAS",
        cnpj=provider.document,
        pfx_bytes=_pfx(),
        password="secret",
        provider=provider,
        key_usage=["das", "nfse"],
    )


@pytest.fixture
def guia(tenant_a, provider, cert_a1):
    return emitir_guia(
        tenant=tenant_a,
        idempotency_key="das-delivery-1",
        provider=provider,
        tipo_guia=GuiaFiscal.TipoGuia.DAS,
        competencia="2024-06",
    )


def _configure_delivery(tenant, **extra):
    das = {
        "enabled": True,
        "email_auto": True,
        "whatsapp_auto": True,
        "accountant_email": "contador@escritorio.com.br",
        "accountant_whatsapp": "+5511987654321",
        "use_nfe_notify_email_for_das": False,
    }
    das.update(extra)
    tenant.settings = {
        **(tenant.settings or {}),
        "das_delivery": das,
        "notify_phone": "+5511999999999",
        "nfe_notify_email": "fiscal@escritorio.com.br",
    }
    tenant.save(update_fields=["settings"])


@pytest.mark.django_db
def test_resolve_email_fallback_off(tenant_a, guia):
    tenant_a.settings = {
        "nfe_notify_email": "fiscal@escritorio.com.br",
        "das_delivery": {"use_nfe_notify_email_for_das": False},
    }
    tenant_a.save(update_fields=["settings"])
    assert resolve_accountant_email(guia) == ""


@pytest.mark.django_db
def test_resolve_email_fallback_on(tenant_a, guia):
    tenant_a.settings = {
        "nfe_notify_email": "fiscal@escritorio.com.br",
        "das_delivery": {"use_nfe_notify_email_for_das": True},
    }
    tenant_a.save(update_fields=["settings"])
    assert resolve_accountant_email(guia) == "fiscal@escritorio.com.br"


@pytest.mark.django_db
def test_deliver_email_happy_path(tenant_a, guia, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _configure_delivery(tenant_a)
    guia.tenant = tenant_a

    assert deliver_guia_email(guia=guia) is True
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["contador@escritorio.com.br"]
    assert "DAS 2024-06" in msg.subject
    assert len(msg.attachments) == 1
    guia.refresh_from_db()
    assert guia.metadata["delivery"]["email_sent"] is True


@pytest.mark.django_db
def test_deliver_email_idempotent(tenant_a, guia, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _configure_delivery(tenant_a)
    guia.tenant = tenant_a
    deliver_guia_email(guia=guia)
    assert deliver_guia_email(guia=guia) is False
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_darf_subject(tenant_a, provider, cert_a1, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _configure_delivery(tenant_a)
    g = emitir_guia(
        tenant=tenant_a,
        idempotency_key="das-darf-1",
        provider=provider,
        tipo_guia=GuiaFiscal.TipoGuia.DARF,
        competencia="2024-10",
    )
    g.tenant = tenant_a
    deliver_guia_email(guia=g)
    assert "DARF 2024-10" in mail.outbox[0].subject


@pytest.mark.django_db
def test_whatsapp_happy_path(tenant_a, guia):
    _configure_delivery(tenant_a)
    guia.tenant = tenant_a
    assert deliver_guia_to_accountant(guia=guia, channels=["whatsapp"]) is True
    notes = ChannelNotification.objects.filter(tenant=tenant_a).order_by("created_at")
    assert notes.filter(event_type="guia_fiscal.available").exists()
    assert notes.filter(event_type="guia_fiscal.available.pdf").exists()
    guia.refresh_from_db()
    assert guia.metadata["delivery"]["whatsapp_sent"] is True


@pytest.mark.django_db
def test_ops_text_without_pdf(tenant_a, guia):
    _configure_delivery(tenant_a)
    handle_guia_delivery_outbox(tenant=tenant_a, guia_id=guia.id, payload={})
    ops = ChannelNotification.objects.get(tenant=tenant_a, event_type="guia_fiscal.ops")
    assert "Enviado ao contador" in ops.message_body
    assert ChannelNotification.objects.filter(
        tenant=tenant_a, event_type="guia_fiscal.available.pdf", phone_e164="+5511999999999"
    ).count() == 0


@pytest.mark.django_db
def test_delivery_failure_does_not_change_status(tenant_a, guia, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _configure_delivery(tenant_a)
    guia.tenant = tenant_a
    with patch("apps.das.delivery.EmailMessage.send", side_effect=OSError("smtp down")):
        with pytest.raises(DasEmailDeliveryError):
            deliver_guia_email(guia=guia)
    guia.refresh_from_db()
    assert guia.status == GuiaFiscal.Status.DISPONIVEL


@pytest.mark.django_db
def test_outbox_handler(tenant_a, guia, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _configure_delivery(tenant_a)
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="guia_fiscal.available",
        aggregate_type="guia_fiscal",
        aggregate_id=guia.id,
        payload={},
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    assert len(mail.outbox) == 1
    assert ChannelNotification.objects.filter(
        tenant=tenant_a, event_type="guia_fiscal.ops"
    ).exists()


@pytest.mark.django_db
def test_resend_api_returns_202(api_client, auth_header, tenant_a, guia):
    _configure_delivery(tenant_a)
    url = f"/api/v1/das/guias/{guia.id}/resend-delivery/"
    before = OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="guia_fiscal.redelivery_requested"
    ).count()
    response = api_client.post(
        url,
        {"force": True, "channels": ["email", "whatsapp"]},
        format="json",
        **auth_header,
    )
    assert response.status_code == 202
    assert response.data["code"] == "das_redelivery_queued"
    assert (
        OutboxMessage.objects.filter(
            tenant=tenant_a, event_type="guia_fiscal.redelivery_requested"
        ).count()
        == before + 1
    )


@pytest.mark.django_db
def test_resend_unknown_guia_404(api_client, auth_header):
    import uuid

    url = f"/api/v1/das/guias/{uuid.uuid4()}/resend-delivery/"
    response = api_client.post(url, {"force": True}, format="json", **auth_header)
    assert response.status_code == 404
