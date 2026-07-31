"""Webhook Inter → paid (inbox + enrich leve)."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.conf import settings
from django.utils import timezone

from apps.billing.due_date_rules import min_due_date
from apps.billing.models import Charge, PaymentEvent, WebhookInbox
from apps.billing.services import create_charge, ingest_gateway_webhook
from apps.master_data.services import create_customer
from apps.ops.models import OutboxMessage
from integrations.payments.port import ChargeRegisterResult


def _sign(payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(
        settings.WEBHOOK_GATEWAY_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return body, signature


def _due():
    return min_due_date() + timedelta(days=7)


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


@pytest.mark.django_db
def test_inter_webhook_recebido_pays(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="wh-inter-full",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    payload = {
        "cobranca": {
            "codigoSolicitacao": charge.gateway_ref,
            "situacao": "RECEBIDO",
            "valorNominal": 50.0,
            "valorTotalRecebido": 50.0,
            "dataSituacao": timezone.now().isoformat(),
            "seuNumero": charge.seu_numero or "X",
        }
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.PROCESSED
    assert inbox.provider == "inter"
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert PaymentEvent.objects.filter(charge=charge).count() == 1
    assert OutboxMessage.objects.filter(
        aggregate_id=charge.id, event_type="charge.paid"
    ).exists()


@pytest.mark.django_db
def test_inter_webhook_amount_mismatch(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="wh-inter-amt",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    payload = {
        "cobranca": {
            "codigoSolicitacao": charge.gateway_ref,
            "situacao": "RECEBIDO",
            "valorTotalRecebido": 1.0,
            "dataSituacao": timezone.now().isoformat(),
        }
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.FAILED
    assert "incompatível" in inbox.error_message.lower()
    charge.refresh_from_db()
    assert charge.status == Charge.Status.REGISTERED
    assert PaymentEvent.objects.count() == 0


@pytest.mark.django_db
def test_inter_webhook_a_receber_does_not_pay(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="wh-inter-ar",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    payload = {
        "cobranca": {
            "codigoSolicitacao": charge.gateway_ref,
            "situacao": "A_RECEBER",
            "valorNominal": 50.0,
        }
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.PROCESSED
    charge.refresh_from_db()
    assert charge.status == Charge.Status.REGISTERED
    assert PaymentEvent.objects.count() == 0


@pytest.mark.django_db
def test_inter_light_webhook_enriches_then_pays(
    tenant_a, customer, monkeypatch, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="wh-inter-light",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )

    fake = MagicMock()
    fake.kind = "inter"
    fake.consultar_cobranca.return_value = ChargeRegisterResult(
        external_ref=charge.gateway_ref,
        status=Charge.Status.PAID,
        raw={"cobranca": {"situacao": "RECEBIDO"}},
        digitable_line="23793",
        barcode="2379",
        extras={
            "situacao": "RECEBIDO",
            "data_situacao": timezone.now().isoformat(),
            "received_cents": 5000,
        },
    )
    monkeypatch.setattr(
        "apps.billing.services.get_payment_gateway",
        lambda **kwargs: fake,
    )

    payload = {"codigoSolicitacao": charge.gateway_ref}
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.PROCESSED
    assert fake.consultar_cobranca.called
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert charge.digitable_line == "23793"
    assert PaymentEvent.objects.filter(charge=charge).count() == 1


@pytest.mark.django_db
def test_inter_webhook_idempotent(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="wh-inter-idem",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    payload = {
        "cobranca": {
            "codigoSolicitacao": charge.gateway_ref,
            "situacao": "RECEBIDO",
            "valorTotalRecebido": 50.0,
            "dataSituacao": "2026-07-20T12:00:00-03:00",
        }
    }
    body, signature = _sign(payload)
    first = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    second = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert first.id == second.id
    assert PaymentEvent.objects.filter(charge=charge).count() == 1
