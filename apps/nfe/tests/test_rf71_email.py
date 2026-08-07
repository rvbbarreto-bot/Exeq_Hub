"""U15-UI + RF-71 e-mail NF-e autorizada."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.email_delivery import (
    NfeEmailDeliveryError,
    deliver_authorized_email,
    resolve_nfe_email_recipient,
)
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "hub@exeq.test"
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
def customer_mail(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente Mail",
        email="tomador@example.com",
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


def _emit(tenant, provider, customer, key="em1"):
    product = create_product(
        tenant=tenant,
        code=f"EM-{key[:4]}",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key=key,
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    return emit_invoice(inv)


@pytest.mark.django_db
def test_rf71_deliver_email_with_attachments(
    nfe_settings, tenant_a, provider_sp, customer_mail
):
    mail.outbox.clear()
    inv = _emit(tenant_a, provider_sp, customer_mail, "rf71-a")
    inv.refresh_from_db()
    assert deliver_authorized_email(invoice=inv) is True
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "tomador@example.com" in msg.to
    assert len(msg.attachments) >= 1
    inv.refresh_from_db()
    assert inv.last_validation.get("email_sent") is True
    # idempotent
    assert deliver_authorized_email(invoice=inv) is False
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_rf71_outbox_sends_email_keeps_authorized(
    nfe_settings, tenant_a, provider_sp, customer_mail
):
    mail.outbox.clear()
    inv = _emit(tenant_a, provider_sp, customer_mail, "rf71-b")
    inv.refresh_from_db()
    msg = OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.authorized", aggregate_id=inv.id
    ).first()
    assert msg is not None
    msg.status = OutboxMessage.Status.PENDING
    msg.attempts = 0
    msg.available_at = timezone.now()
    msg.save(update_fields=["status", "attempts", "available_at", "updated_at"])
    assert claim_and_dispatch(str(msg.id)) == "processed"
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_rf71_email_failure_fails_outbox_not_status(
    nfe_settings, tenant_a, provider_sp, customer_mail
):
    inv = _emit(tenant_a, provider_sp, customer_mail, "rf71-c")
    inv.refresh_from_db()
    msg = OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.authorized", aggregate_id=inv.id
    ).first()
    msg.status = OutboxMessage.Status.PENDING
    msg.attempts = 0
    msg.available_at = timezone.now()
    msg.save(update_fields=["status", "attempts", "available_at", "updated_at"])

    with patch(
        "apps.nfe.email_delivery.EmailMessage.send",
        side_effect=RuntimeError("smtp down"),
    ):
        assert claim_and_dispatch(str(msg.id)) == "failed"
    msg.refresh_from_db()
    assert msg.status == OutboxMessage.Status.FAILED
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED


@pytest.mark.django_db
def test_rf71_resend_api(
    api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_mail
):
    mail.outbox.clear()
    inv = _emit(tenant_a, provider_sp, customer_mail, "rf71-d")
    inv.refresh_from_db()
    url = reverse("nfe-invoice-resend-email", kwargs={"pk": inv.id})
    res = api_client.post(url, {"email": "outro@example.com"}, format="json", **auth_header)
    assert res.status_code == 200, res.data
    assert "resend_email" in res.data["allowed_actions"]
    assert len(mail.outbox) == 1
    assert "outro@example.com" in mail.outbox[0].to


@pytest.mark.django_db
def test_rf71_resolve_tenant_notify_email(nfe_settings, tenant_a, provider_sp, customer_mail):
    customer_mail.email = ""
    customer_mail.save(update_fields=["email"])
    inv = _emit(tenant_a, provider_sp, customer_mail, "rf71-e")
    inv.refresh_from_db()
    assert resolve_nfe_email_recipient(inv) == ""
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_notify_email": "ops@exeq.local"}
    tenant_a.save(update_fields=["settings"])
    inv.refresh_from_db()
    # re-fetch tenant relation
    inv = NfeInvoice.objects.select_related("tenant", "customer").get(pk=inv.pk)
    assert resolve_nfe_email_recipient(inv) == "ops@exeq.local"


@pytest.mark.django_db
def test_rf71_force_resend(
    nfe_settings, tenant_a, provider_sp, customer_mail
):
    mail.outbox.clear()
    inv = _emit(tenant_a, provider_sp, customer_mail, "rf71-f")
    deliver_authorized_email(invoice=inv)
    inv.refresh_from_db()
    assert deliver_authorized_email(invoice=inv, force=True) is True
    assert len(mail.outbox) == 2
