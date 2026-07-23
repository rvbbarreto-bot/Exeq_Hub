"""D1/D2 — webhook Inter register / retry (estudo §9)."""

import pytest

from apps.billing.exceptions import (
    InvalidPaymentProviderError,
    InvalidProviderCredentialsError,
)
from apps.billing.models import PaymentProviderAudit, WebhookInbox
from apps.billing.provider_services import (
    delete_inter_webhook,
    get_inter_webhook,
    register_inter_webhook,
    resolve_inter_webhook_url,
    retry_inter_webhook_callbacks,
    set_billing_provider,
)
from integrations.payments.banks import InterPaymentGateway
from integrations.payments.errors import PaymentGatewayError


def test_resolve_webhook_url_requires_https(settings):
    settings.DEBUG = True
    settings.INTER_WEBHOOK_PUBLIC_URL = ""
    with pytest.raises(InvalidProviderCredentialsError):
        resolve_inter_webhook_url()
    with pytest.raises(InvalidProviderCredentialsError):
        resolve_inter_webhook_url("http://evil.example/hook")
    assert resolve_inter_webhook_url("https://hub.example/api/v1/webhooks/gateway").startswith(
        "https://"
    )
    assert resolve_inter_webhook_url("http://127.0.0.1:8000/api/v1/webhooks/gateway")


def test_inter_stub_webhook_ops():
    gw = InterPaymentGateway(mode="stub", token="")
    put = gw.registrar_webhook(webhook_url="https://hub.example/api/v1/webhooks/gateway")
    assert put["action"] == "registrar_webhook"
    assert put["webhookUrl"].startswith("https://")
    get = gw.consultar_webhook()
    assert get["action"] == "consultar_webhook"
    delete = gw.remover_webhook()
    assert delete["action"] == "remover_webhook"
    retry = gw.retry_webhook_callbacks(codigo_solicitacao=["a", "b"])
    assert retry["codigoSolicitacao"] == ["a", "b"]


def test_inter_retry_rejects_over_max(settings):
    settings.INTER_WEBHOOK_RETRY_MAX = 2
    gw = InterPaymentGateway(mode="stub", token="")
    with pytest.raises(PaymentGatewayError, match="Máximo"):
        gw.retry_webhook_callbacks(codigo_solicitacao=["1", "2", "3"])


@pytest.mark.django_db
def test_register_inter_webhook_stub(tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"
    settings.PAYMENT_DEFAULT_PROVIDER = "inter"
    out = register_inter_webhook(tenant=tenant_a)
    assert out["status"] == "ok"
    assert out["webhookUrl"].endswith("/webhooks/gateway")
    assert PaymentProviderAudit.objects.filter(
        action=PaymentProviderAudit.Action.WEBHOOK_CONFIGURED
    ).exists()


@pytest.mark.django_db
def test_get_delete_inter_webhook_stub(tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"
    assert get_inter_webhook(tenant=tenant_a)["status"] == "ok"
    assert delete_inter_webhook(tenant=tenant_a)["status"] == "ok"


@pytest.mark.django_db
def test_set_provider_inter_auto_registers_webhook(tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"
    tenant_a.settings = {"payment_provider": "asaas"}
    tenant_a.save(update_fields=["settings"])
    out = set_billing_provider(tenant=tenant_a, provider="inter")
    assert out["provider"] == "inter"
    assert out.get("webhook", {}).get("status") == "ok"


@pytest.mark.django_db
def test_retry_callbacks_and_local_inbox(
    tenant_a, settings, monkeypatch
):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"

    inbox = WebhookInbox.objects.create(
        tenant=tenant_a,
        provider="inter",
        idempotency_key="retry-local-1",
        status=WebhookInbox.Status.FAILED,
        signature_valid=True,
        raw_payload={
            "gateway_ref": "sol-retry-1",
            "amount_cents": 5000,
            "hub_status": "paid",
            "idempotency_key": "retry-local-1",
        },
        payload_hash=WebhookInbox.hash_payload({"x": 1}),
        error_message="Valor incompatível",
    )

    called = {}

    def _fake_reprocess(row):
        called["id"] = str(row.id)
        row.status = WebhookInbox.Status.PROCESSED
        row.save(update_fields=["status", "updated_at"])
        return row

    monkeypatch.setattr(
        "apps.billing.services.reprocess_webhook", _fake_reprocess
    )

    out = retry_inter_webhook_callbacks(
        tenant=tenant_a,
        codigo_solicitacao=["sol-retry-1"],
        reprocess_local_inbox=True,
    )
    assert out["status"] == "ok"
    assert str(inbox.id) in out["inbox_reprocessed"]
    assert called["id"] == str(inbox.id)


@pytest.mark.django_db
def test_api_inter_webhook_put_get_delete(api_client, auth_header, tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"

    put = api_client.put(
        "/api/v1/billing/providers/inter/webhook",
        {"webhookUrl": "https://hub.example/api/v1/webhooks/gateway"},
        format="json",
        **auth_header,
    )
    assert put.status_code == 200
    assert put.data["status"] == "ok"

    get = api_client.get(
        "/api/v1/billing/providers/inter/webhook",
        **auth_header,
    )
    assert get.status_code == 200

    delete = api_client.delete(
        "/api/v1/billing/providers/inter/webhook",
        **auth_header,
    )
    assert delete.status_code == 200


@pytest.mark.django_db
def test_api_inter_webhook_retry(api_client, auth_header, tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    retry = api_client.post(
        "/api/v1/billing/providers/inter/webhook/callbacks/retry",
        {"codigoSolicitacao": ["sol-1", "sol-2"], "reprocess_local_inbox": False},
        format="json",
        **auth_header,
    )
    assert retry.status_code == 200
    assert retry.data["codigoSolicitacao"] == ["sol-1", "sol-2"]


@pytest.mark.django_db
def test_register_rejects_non_inter_provider(tenant_a, settings):
    settings.INTER_WEBHOOK_PUBLIC_URL = "https://hub.example/api/v1/webhooks/gateway"
    tenant_a.settings = {"payment_provider": "asaas"}
    tenant_a.save(update_fields=["settings"])
    with pytest.raises(InvalidPaymentProviderError):
        register_inter_webhook(tenant=tenant_a)
