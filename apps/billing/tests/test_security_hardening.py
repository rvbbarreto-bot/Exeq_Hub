"""Testes de hardenings de segurança (webhook / secrets / tenant resolve)."""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.billing.due_date_rules import min_due_date
from apps.billing.exceptions import ChargeNotFoundError
from apps.billing.models import Charge, PaymentEvent, WebhookInbox
from apps.billing.services import (
    create_charge,
    ingest_gateway_webhook,
    verify_gateway_signature,
)
from apps.billing.webhook_security import webhook_ip_allowed
from apps.master_data.services import create_customer
from shared.security_checks import assert_secure_runtime_settings


def _due():
    return min_due_date() + timedelta(days=7)


def _sign(payload: dict, secret: str | None = None) -> tuple[bytes, str]:
    from django.conf import settings

    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    key = (secret or settings.WEBHOOK_GATEWAY_SECRET).encode()
    signature = hmac.new(key, body, hashlib.sha256).hexdigest()
    return body, signature


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


def test_assert_secure_rejects_weak_webhook_secret(settings):
    settings.DEBUG = False
    settings.FORCE_SECURE_SECRETS = False
    settings.WEBHOOK_GATEWAY_SECRET = "dev-webhook-secret"
    settings.FIELD_ENCRYPTION_KEY = "ok-not-the-example-key-but-long-enough!!!!"
    with pytest.raises(ImproperlyConfigured, match="WEBHOOK_GATEWAY_SECRET"):
        assert_secure_runtime_settings()


def test_assert_secure_ok_with_strong_secrets(settings):
    settings.DEBUG = False
    settings.WEBHOOK_GATEWAY_SECRET = "x" * 32
    settings.FIELD_ENCRYPTION_KEY = "different-from-repo-example-key===="
    assert_secure_runtime_settings()


def test_verify_signature_accepts_sha256_prefix(settings):
    settings.WEBHOOK_GATEWAY_SECRET = "unit-test-secret-with-32-chars!!"
    body = b'{"a":1}'
    sig = hmac.new(
        settings.WEBHOOK_GATEWAY_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    assert verify_gateway_signature(body=body, signature=f"sha256={sig}")
    assert not verify_gateway_signature(body=body, signature="bad")


def test_webhook_ip_allowlist(rf, settings):
    settings.WEBHOOK_ALLOWED_IPS = ["203.0.113.10"]
    settings.WEBHOOK_TRUST_X_FORWARDED_FOR = False
    req = rf.post("/api/v1/webhooks/gateway", REMOTE_ADDR="203.0.113.10")
    assert webhook_ip_allowed(req) is True
    req2 = rf.post("/api/v1/webhooks/gateway", REMOTE_ADDR="198.51.100.1")
    assert webhook_ip_allowed(req2) is False


@pytest.mark.django_db
def test_resolve_tenant_rejects_global_seu_numero(
    tenant_a, customer, settings
):
    from apps.billing.services import _resolve_tenant

    settings.PAYMENT_HTTP_MODE = "stub"
    create_charge(
        tenant=tenant_a,
        idempotency_key="sec-seu",
        customer=customer,
        amount_cents=500,
        due_date=_due(),
        seu_numero="CTRLSEC01",
    )
    with pytest.raises(ChargeNotFoundError, match="tenant_slug ausente"):
        _resolve_tenant(
            {
                "external_reference": "CTRLSEC01",
                "idempotency_key": "wh-seu-only",
            }
        )


@pytest.mark.django_db
def test_webhook_second_idempotency_does_not_duplicate_payment_event(
    tenant_a, customer, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="sec-replay",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    base = {
        "tenant_slug": tenant_a.slug,
        "gateway_ref": charge.gateway_ref,
        "amount_cents": 5000,
        "paid_at": timezone.now().isoformat(),
    }
    p1 = {**base, "idempotency_key": "pay-1"}
    p2 = {**base, "idempotency_key": "pay-2"}
    b1, s1 = _sign(p1)
    b2, s2 = _sign(p2)
    ingest_gateway_webhook(raw_body=b1, signature=s1, payload=p1)
    ingest_gateway_webhook(raw_body=b2, signature=s2, payload=p2)
    assert PaymentEvent.objects.filter(charge=charge).count() == 1
    assert WebhookInbox.objects.filter(tenant=tenant_a).count() == 2


@pytest.mark.django_db
def test_webhook_api_rejects_disallowed_ip(
    api_client, tenant_a, customer, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.WEBHOOK_ALLOWED_IPS = ["203.0.113.10"]
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="sec-ip",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    payload = {
        "tenant_slug": tenant_a.slug,
        "idempotency_key": "wh-ip-1",
        "gateway_ref": charge.gateway_ref,
        "amount_cents": 5000,
        "paid_at": timezone.now().isoformat(),
    }
    body, signature = _sign(payload)
    res = api_client.post(
        "/api/v1/webhooks/gateway",
        data=body,
        content_type="application/json",
        HTTP_X_WEBHOOK_SIGNATURE=signature,
        REMOTE_ADDR="198.51.100.1",
    )
    assert res.status_code == 403


def test_prod_webhook_url_ignores_arbitrary_client_url(settings):
    from apps.billing.exceptions import InvalidProviderCredentialsError
    from apps.billing.provider_services import resolve_inter_webhook_url

    settings.DEBUG = False
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"
    assert resolve_inter_webhook_url() == settings.INTER_WEBHOOK_PUBLIC_URL
    with pytest.raises(InvalidProviderCredentialsError, match="coincidir"):
        resolve_inter_webhook_url("https://evil.example/steal")
    # URL idêntica (trailing slash) aceita
    assert resolve_inter_webhook_url(
        "https://hub.example/api/v1/webhooks/gateway/"
    ).rstrip("/") == settings.INTER_WEBHOOK_PUBLIC_URL.rstrip("/")


def test_env_inter_fallback_disabled_with_tenant(settings, tenant_a):
    from integrations.payments.inter_auth import resolve_inter_credentials

    settings.ALLOW_ENV_INTER_CREDENTIALS_FALLBACK = False
    settings.INTER_CLIENT_ID = "env-client-should-not-bleed"
    settings.INTER_CLIENT_SECRET = "env-secret"
    creds = resolve_inter_credentials(tenant=tenant_a)
    assert creds.client_id == ""
    assert creds.client_secret == ""


@pytest.mark.django_db
def test_resolve_ambiguous_gateway_ref(tenant_a, tenant_b, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    from apps.master_data.services import create_customer

    cust_b = create_customer(
        tenant=tenant_b,
        document="39053344705",
        document_type="cpf",
        name="Outro",
    )
    c1 = create_charge(
        tenant=tenant_a,
        idempotency_key="amb-a",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    c2 = create_charge(
        tenant=tenant_b,
        idempotency_key="amb-b",
        customer=cust_b,
        amount_cents=5000,
        due_date=_due(),
    )
    # Força colisão artificial de gateway_ref (sandbox normalmente único).
    Charge.objects.filter(id=c2.id).update(gateway_ref=c1.gateway_ref)
    payload = {
        "idempotency_key": "wh-amb",
        "gateway_ref": c1.gateway_ref,
        "amount_cents": 5000,
        "paid_at": timezone.now().isoformat(),
    }
    body, signature = _sign(payload)
    with pytest.raises(ChargeNotFoundError, match="ambíguo"):
        ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)


@pytest.mark.django_db
def test_sync_get_method_not_allowed(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="sec-sync-get",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    res = api_client.get(
        f"/api/v1/charges/{charge.id}/sync/",
        **auth_header,
    )
    assert res.status_code == 405


@pytest.mark.django_db
def test_operator_cannot_put_provider(api_client, tenant_a, roles, settings):
    from apps.accounts.models import TenantMembership, User

    user = User.objects.create_user(
        email="op@exeq.local", password="Secret123!", name="Op"
    )
    TenantMembership.objects.create(
        tenant=tenant_a, user=user, role=roles["operator"]
    )
    login = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": tenant_a.slug,
            "email": "op@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert login.status_code == 200
    res = api_client.put(
        "/api/v1/billing/provider",
        {"provider": "asaas"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
    )
    assert res.status_code == 403
