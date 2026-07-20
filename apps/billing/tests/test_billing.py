import hashlib
import hmac
import json
from datetime import date

import pytest
from django.conf import settings
from django.utils import timezone

from apps.billing.exceptions import InvalidWebhookSignatureError
from apps.billing.models import Charge, PaymentEvent, WebhookInbox
from apps.billing.services import (
    cancel_charge,
    create_charge,
    ingest_gateway_webhook,
    reprocess_webhook,
)
from apps.master_data.services import create_customer
from apps.ops.models import OutboxMessage


def _sign(payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(
        settings.WEBHOOK_GATEWAY_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return body, signature


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


@pytest.mark.django_db
def test_create_charge_uses_tenant_payment_provider(tenant_a, customer):
    tenant_a.settings = {"payment_provider": "c6"}
    tenant_a.save(update_fields=["settings"])
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-c6",
        customer=customer,
        amount_cents=2000,
        due_date=date(2024, 7, 1),
    )
    assert charge.gateway_ref.startswith("c6_")
    assert charge.status == Charge.Status.REGISTERED


@pytest.mark.django_db
def test_create_charge_idempotent(tenant_a, customer):
    kwargs = dict(
        tenant=tenant_a,
        idempotency_key="chg-1",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    first = create_charge(**kwargs)
    second = create_charge(**kwargs)
    assert first.id == second.id
    assert first.status == Charge.Status.REGISTERED
    assert first.gateway_ref.startswith("asaas_")
    assert OutboxMessage.objects.filter(
        aggregate_id=first.id,
        event_type="charge.registered",
    ).exists()


@pytest.mark.django_db
def test_cancel_charge_via_gateway(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-cancel",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    cancel_charge(charge)
    charge.refresh_from_db()
    assert charge.status == Charge.Status.CANCELLED
    assert OutboxMessage.objects.filter(
        aggregate_id=charge.id,
        event_type="charge.cancelled",
    ).exists()


@pytest.mark.django_db
def test_webhook_invalid_signature_rejected(tenant_a, customer):
    create_charge(
        tenant=tenant_a,
        idempotency_key="chg-2",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    payload = {"tenant_slug": "acme", "idempotency_key": "wh-1"}
    body = json.dumps(payload).encode()
    with pytest.raises(InvalidWebhookSignatureError):
        ingest_gateway_webhook(raw_body=body, signature="bad", payload=payload)
    assert WebhookInbox.objects.count() == 0
    assert PaymentEvent.objects.count() == 0


@pytest.mark.django_db
def test_webhook_pays_charge_once(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-3",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    payload = {
        "tenant_slug": "acme",
        "idempotency_key": "wh-pay-1",
        "gateway_ref": charge.gateway_ref,
        "amount_cents": 5000,
        "paid_at": timezone.now().isoformat(),
    }
    body, signature = _sign(payload)
    first = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    second = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert first.id == second.id
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert PaymentEvent.objects.filter(charge=charge).count() == 1


@pytest.mark.django_db
def test_webhook_incompatible_amount_does_not_pay(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-amt",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    payload = {
        "tenant_slug": "acme",
        "idempotency_key": "wh-amt-1",
        "gateway_ref": charge.gateway_ref,
        "amount_cents": 100,
        "paid_at": timezone.now().isoformat(),
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.FAILED
    charge.refresh_from_db()
    assert charge.status == Charge.Status.REGISTERED
    assert PaymentEvent.objects.count() == 0


@pytest.mark.django_db
def test_reprocess_failed_webhook_idempotent(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-repro",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    payload = {
        "tenant_slug": "acme",
        "idempotency_key": "wh-repro-1",
        "gateway_ref": charge.gateway_ref,
        "amount_cents": 1,
        "paid_at": timezone.now().isoformat(),
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.FAILED

    inbox.raw_payload = {**payload, "amount_cents": 5000}
    inbox.save(update_fields=["raw_payload", "updated_at"])
    first = reprocess_webhook(inbox)
    second = reprocess_webhook(first)
    assert first.id == second.id
    assert first.status == WebhookInbox.Status.PROCESSED
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert PaymentEvent.objects.filter(charge=charge).count() == 1


@pytest.mark.django_db
def test_asaas_like_webhook_normalized(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-asaas",
        customer=customer,
        amount_cents=5000,
        due_date=date(2024, 7, 1),
    )
    payload = {
        "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": charge.gateway_ref,
            "value": 50.0,
            "externalReference": str(charge.id),
            "confirmedDate": timezone.now().isoformat(),
        },
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.PROCESSED
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID


@pytest.mark.django_db
def test_charges_and_webhook_api(api_client, auth_header, tenant_a, customer):
    create = api_client.post(
        "/api/v1/charges/",
        {
            "idempotency_key": "api-chg-1",
            "customer_id": str(customer.id),
            "amount_cents": 1500,
            "due_date": "2024-08-01",
            "description": "Teste",
        },
        format="json",
        **auth_header,
    )
    assert create.status_code == 201
    gateway_ref = create.data["gateway_ref"]

    payload = {
        "tenant_slug": "acme",
        "idempotency_key": "api-wh-1",
        "gateway_ref": gateway_ref,
        "amount_cents": 1500,
        "paid_at": timezone.now().isoformat(),
    }
    body, signature = _sign(payload)
    webhook = api_client.post(
        "/api/v1/webhooks/gateway",
        data=body,
        content_type="application/json",
        HTTP_X_WEBHOOK_SIGNATURE=signature,
    )
    assert webhook.status_code == 200
    assert webhook.data["status"] == "processed"

    bad = api_client.post(
        "/api/v1/webhooks/gateway",
        data=body,
        content_type="application/json",
        HTTP_X_WEBHOOK_SIGNATURE="nope",
    )
    assert bad.status_code == 401
