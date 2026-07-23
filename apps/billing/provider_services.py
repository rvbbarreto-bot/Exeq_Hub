"""Configuração do provedor de cobrança por tenant (sem cadastro FEBRABAN)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import TenantSecret
from apps.accounts.secrets import get_tenant_secret_plaintext, set_tenant_secret
from apps.billing.exceptions import (
    InvalidPaymentProviderError,
    InvalidProviderCredentialsError,
)
from apps.billing.models import PaymentProviderAudit
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.inter_auth import build_inter_auth_client
from integrations.payments.inter_mtls import build_inter_mtls_context
from integrations.payments.router import (
    KNOWN_PAYMENT_PROVIDERS,
    PROVIDER_ASAAS,
    PROVIDER_C6,
    PROVIDER_INTER,
    resolve_payment_provider_kind,
)

INTER_SECRET_KEYS = (
    "client_id",
    "client_secret",
    "cert_pem",
    "key_pem",
    "conta_corrente",
)
TOKEN_PROVIDERS = frozenset({PROVIDER_ASAAS, PROVIDER_C6})


def mask_secret(value: str | None, *, visible: int = 4) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= visible:
        return "*" * len(text)
    return text[:visible] + "****"


def _secret_updated_at(*, tenant, provider: str, key_name: str):
    try:
        row = TenantSecret.objects.get(
            tenant=tenant, provider=provider, key_name=key_name
        )
    except TenantSecret.DoesNotExist:
        return None
    return row.updated_at


def _has_secret(*, tenant, provider: str, key_name: str) -> bool:
    return TenantSecret.objects.filter(
        tenant=tenant, provider=provider, key_name=key_name
    ).exists()


def _provider_configured(*, tenant, provider: str) -> bool:
    if provider == PROVIDER_INTER:
        return all(
            _has_secret(tenant=tenant, provider=PROVIDER_INTER, key_name=k)
            for k in ("client_id", "client_secret", "cert_pem", "key_pem")
        )
    if provider in TOKEN_PROVIDERS:
        return _has_secret(tenant=tenant, provider=provider, key_name="api_token")
    return False


def get_billing_provider_status(*, tenant) -> dict:
    active = resolve_payment_provider_kind(tenant=tenant)
    providers = {}
    for kind in sorted(KNOWN_PAYMENT_PROVIDERS):
        providers[kind] = {"configured": _provider_configured(tenant=tenant, provider=kind)}
    return {
        "provider": active,
        "providers": providers,
    }


@transaction.atomic
def set_billing_provider(*, tenant, provider: str, actor_user=None) -> dict:
    kind = str(provider or "").lower().strip()
    if kind not in KNOWN_PAYMENT_PROVIDERS:
        raise InvalidPaymentProviderError(
            f"Provedor inválido: {provider}. Use: {', '.join(sorted(KNOWN_PAYMENT_PROVIDERS))}"
        )
    settings_map = dict(tenant.settings or {})
    previous = settings_map.get("payment_provider")
    settings_map["payment_provider"] = kind
    tenant.settings = settings_map
    tenant.save(update_fields=["settings", "updated_at"])
    PaymentProviderAudit.objects.create(
        tenant=tenant,
        provider=kind,
        action=PaymentProviderAudit.Action.PROVIDER_CHANGED,
        actor_user=actor_user,
        metadata={"previous": previous, "provider": kind},
    )
    status_payload = get_billing_provider_status(tenant=tenant)
    # D1 — ao ativar Inter, tenta cadastrar webhook se URL pública estiver configurada.
    if kind == PROVIDER_INTER:
        from django.conf import settings

        if (getattr(settings, "INTER_WEBHOOK_PUBLIC_URL", "") or "").strip():
            try:
                status_payload["webhook"] = register_inter_webhook(
                    tenant=tenant, actor_user=actor_user
                )
            except (PaymentGatewayError, InvalidProviderCredentialsError) as exc:
                status_payload["webhook"] = {
                    "status": "error",
                    "detail": str(exc)[:300],
                }
    return status_payload


def get_inter_credentials_metadata(*, tenant) -> dict:
    client_id = get_tenant_secret_plaintext(
        tenant=tenant, provider=PROVIDER_INTER, key_name="client_id"
    )
    conta = get_tenant_secret_plaintext(
        tenant=tenant, provider=PROVIDER_INTER, key_name="conta_corrente"
    )
    timestamps = [
        _secret_updated_at(tenant=tenant, provider=PROVIDER_INTER, key_name=k)
        for k in INTER_SECRET_KEYS
    ]
    timestamps = [t for t in timestamps if t is not None]
    last_updated = max(timestamps) if timestamps else None
    return {
        "provider": PROVIDER_INTER,
        "configured": _provider_configured(tenant=tenant, provider=PROVIDER_INTER),
        "client_id_masked": mask_secret(client_id),
        "has_client_secret": _has_secret(
            tenant=tenant, provider=PROVIDER_INTER, key_name="client_secret"
        ),
        "has_cert": _has_secret(
            tenant=tenant, provider=PROVIDER_INTER, key_name="cert_pem"
        ),
        "has_key": _has_secret(
            tenant=tenant, provider=PROVIDER_INTER, key_name="key_pem"
        ),
        "conta_corrente_masked": mask_secret(conta),
        "updated_at": last_updated.isoformat() if last_updated else None,
    }


def get_token_provider_metadata(*, tenant, provider: str) -> dict:
    kind = str(provider or "").lower().strip()
    if kind not in TOKEN_PROVIDERS:
        raise InvalidPaymentProviderError(f"Provedor inválido para token: {provider}")
    token = get_tenant_secret_plaintext(
        tenant=tenant, provider=kind, key_name="api_token"
    )
    updated = _secret_updated_at(tenant=tenant, provider=kind, key_name="api_token")
    return {
        "provider": kind,
        "configured": bool(token),
        "api_token_masked": mask_secret(token),
        "updated_at": updated.isoformat() if updated else None,
    }


@transaction.atomic
def save_inter_credentials(
    *,
    tenant,
    client_id: str,
    client_secret: str,
    cert_pem: str,
    key_pem: str,
    conta_corrente: str = "",
    actor_user=None,
) -> dict:
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    cert_pem = (cert_pem or "").strip()
    key_pem = (key_pem or "").strip()
    conta_corrente = (conta_corrente or "").strip()
    if not client_id or not client_secret or not cert_pem or not key_pem:
        raise InvalidProviderCredentialsError(
            "client_id, client_secret, cert_file e key_file são obrigatórios"
        )
    try:
        mtls = build_inter_mtls_context(cert_pem=cert_pem, key_pem=key_pem)
        mtls.close()
    except PaymentGatewayError as exc:
        raise InvalidProviderCredentialsError(
            f"Par certificado/chave inválido: {exc}"
        ) from exc

    set_tenant_secret(
        tenant=tenant, provider=PROVIDER_INTER, key_name="client_id", plaintext=client_id
    )
    set_tenant_secret(
        tenant=tenant,
        provider=PROVIDER_INTER,
        key_name="client_secret",
        plaintext=client_secret,
    )
    set_tenant_secret(
        tenant=tenant, provider=PROVIDER_INTER, key_name="cert_pem", plaintext=cert_pem
    )
    set_tenant_secret(
        tenant=tenant, provider=PROVIDER_INTER, key_name="key_pem", plaintext=key_pem
    )
    if conta_corrente:
        set_tenant_secret(
            tenant=tenant,
            provider=PROVIDER_INTER,
            key_name="conta_corrente",
            plaintext=conta_corrente,
        )

    PaymentProviderAudit.objects.create(
        tenant=tenant,
        provider=PROVIDER_INTER,
        action=PaymentProviderAudit.Action.CREDENTIALS_UPDATED,
        actor_user=actor_user,
        metadata={
            "keys": ["client_id", "client_secret", "cert_pem", "key_pem"]
            + (["conta_corrente"] if conta_corrente else []),
            "at": timezone.now().isoformat(),
        },
    )
    return get_inter_credentials_metadata(tenant=tenant)


@transaction.atomic
def save_token_provider_credentials(
    *,
    tenant,
    provider: str,
    api_token: str,
    actor_user=None,
) -> dict:
    kind = str(provider or "").lower().strip()
    if kind not in TOKEN_PROVIDERS:
        raise InvalidPaymentProviderError(f"Provedor inválido para token: {provider}")
    token = (api_token or "").strip()
    if not token:
        raise InvalidProviderCredentialsError("api_token obrigatório")
    set_tenant_secret(
        tenant=tenant, provider=kind, key_name="api_token", plaintext=token
    )
    PaymentProviderAudit.objects.create(
        tenant=tenant,
        provider=kind,
        action=PaymentProviderAudit.Action.CREDENTIALS_UPDATED,
        actor_user=actor_user,
        metadata={"keys": ["api_token"], "at": timezone.now().isoformat()},
    )
    return get_token_provider_metadata(tenant=tenant, provider=kind)


def test_inter_connection(*, tenant, actor_user=None) -> dict:
    auth = build_inter_auth_client(tenant=tenant)
    if auth is None:
        PaymentProviderAudit.objects.create(
            tenant=tenant,
            provider=PROVIDER_INTER,
            action=PaymentProviderAudit.Action.CONNECTION_TESTED,
            actor_user=actor_user,
            metadata={"status": "error", "detail": "credenciais incompletas"},
        )
        return {
            "status": "error",
            "detail": "Credenciais Inter incompletas para este tenant",
            "http_status": 400,
        }
    try:
        auth.get_access_token(force=True)
        PaymentProviderAudit.objects.create(
            tenant=tenant,
            provider=PROVIDER_INTER,
            action=PaymentProviderAudit.Action.CONNECTION_TESTED,
            actor_user=actor_user,
            metadata={"status": "ok"},
        )
        return {"status": "ok", "http_status": 200}
    except PaymentGatewayError as exc:
        detail = str(exc)
        for secret_key in ("client_secret", "access_token", "Bearer"):
            detail = detail.replace(secret_key, "[redacted]")
        PaymentProviderAudit.objects.create(
            tenant=tenant,
            provider=PROVIDER_INTER,
            action=PaymentProviderAudit.Action.CONNECTION_TESTED,
            actor_user=actor_user,
            metadata={"status": "error"},
        )
        return {"status": "error", "detail": detail[:300], "http_status": 502}
    finally:
        auth.close()


def resolve_inter_webhook_url(explicit: str | None = None) -> str:
    """Resolve URL pública do Hub para cadastro no Inter (estudo §9.1).

    Em produção (DEBUG=False): ignora URL arbitrária do cliente e usa
    INTER_WEBHOOK_PUBLIC_URL (mitiga hijack de callback).
    """
    from django.conf import settings

    configured = (getattr(settings, "INTER_WEBHOOK_PUBLIC_URL", "") or "").strip()
    requested = (explicit or "").strip()

    if not settings.DEBUG:
        url = configured
        if requested and configured and requested.rstrip("/") != configured.rstrip("/"):
            raise InvalidProviderCredentialsError(
                "webhookUrl deve coincidir com INTER_WEBHOOK_PUBLIC_URL"
            )
    else:
        url = requested or configured

    if not url:
        raise InvalidProviderCredentialsError(
            "Informe webhookUrl ou configure INTER_WEBHOOK_PUBLIC_URL "
            "(HTTPS pública → /api/v1/webhooks/gateway)"
        )
    lower = url.lower()
    allow_http_local = lower.startswith("http://127.0.0.1") or lower.startswith(
        "http://localhost"
    )
    if not (lower.startswith("https://") or allow_http_local):
        raise InvalidProviderCredentialsError(
            "webhookUrl deve ser HTTPS pública (ou http://localhost em dev)"
        )
    return url


def _require_inter_gateway(*, tenant):
    from integrations.payments.factory import get_payment_gateway

    active = resolve_payment_provider_kind(tenant=tenant)
    if active != PROVIDER_INTER:
        raise InvalidPaymentProviderError(
            f"Webhook Cobrança Inter exige provedor ativo 'inter' (atual: {active})"
        )
    gw = get_payment_gateway(tenant=tenant)
    if getattr(gw, "kind", None) != PROVIDER_INTER:
        raise InvalidPaymentProviderError("Gateway ativo não é Inter")
    if not hasattr(gw, "registrar_webhook"):
        raise InvalidPaymentProviderError("Gateway sem suporte a webhook Cobrança")
    return gw


def register_inter_webhook(
    *, tenant, webhook_url: str | None = None, actor_user=None
) -> dict:
    """D1 — PUT webhook no Inter para o tenant."""
    url = resolve_inter_webhook_url(webhook_url)
    gw = _require_inter_gateway(tenant=tenant)
    try:
        raw = gw.registrar_webhook(webhook_url=url)
    except PaymentGatewayError as exc:
        PaymentProviderAudit.objects.create(
            tenant=tenant,
            provider=PROVIDER_INTER,
            action=PaymentProviderAudit.Action.WEBHOOK_CONFIGURED,
            actor_user=actor_user,
            metadata={"status": "error", "op": "put", "detail": str(exc)[:200]},
        )
        raise
    PaymentProviderAudit.objects.create(
        tenant=tenant,
        provider=PROVIDER_INTER,
        action=PaymentProviderAudit.Action.WEBHOOK_CONFIGURED,
        actor_user=actor_user,
        metadata={"status": "ok", "op": "put", "webhookUrl": url},
    )
    return {
        "status": "ok",
        "provider": PROVIDER_INTER,
        "webhookUrl": url,
        "gateway": raw if isinstance(raw, dict) else {"raw": raw},
    }


def get_inter_webhook(*, tenant, actor_user=None) -> dict:
    """D1 — GET webhook cadastrado no Inter."""
    gw = _require_inter_gateway(tenant=tenant)
    try:
        raw = gw.consultar_webhook()
    except PaymentGatewayError as exc:
        raise InvalidProviderCredentialsError(str(exc)) from exc
    return {
        "status": "ok",
        "provider": PROVIDER_INTER,
        "gateway": raw if isinstance(raw, dict) else {"raw": raw},
    }


def delete_inter_webhook(*, tenant, actor_user=None) -> dict:
    """D1 — DELETE webhook no Inter."""
    gw = _require_inter_gateway(tenant=tenant)
    try:
        raw = gw.remover_webhook()
    except PaymentGatewayError as exc:
        PaymentProviderAudit.objects.create(
            tenant=tenant,
            provider=PROVIDER_INTER,
            action=PaymentProviderAudit.Action.WEBHOOK_CONFIGURED,
            actor_user=actor_user,
            metadata={"status": "error", "op": "delete", "detail": str(exc)[:200]},
        )
        raise InvalidProviderCredentialsError(str(exc)) from exc
    PaymentProviderAudit.objects.create(
        tenant=tenant,
        provider=PROVIDER_INTER,
        action=PaymentProviderAudit.Action.WEBHOOK_CONFIGURED,
        actor_user=actor_user,
        metadata={"status": "ok", "op": "delete"},
    )
    return {
        "status": "ok",
        "provider": PROVIDER_INTER,
        "gateway": raw if isinstance(raw, dict) else {"raw": raw},
    }


def retry_inter_webhook_callbacks(
    *,
    tenant,
    codigo_solicitacao: list[str],
    actor_user=None,
    reprocess_local_inbox: bool = True,
) -> dict:
    """D2 — POST retry de callbacks no Inter + opcional reprocess da inbox Hub."""
    refs = [str(x).strip() for x in (codigo_solicitacao or []) if str(x).strip()]
    gw = _require_inter_gateway(tenant=tenant)
    try:
        raw = gw.retry_webhook_callbacks(codigo_solicitacao=refs)
    except PaymentGatewayError as exc:
        PaymentProviderAudit.objects.create(
            tenant=tenant,
            provider=PROVIDER_INTER,
            action=PaymentProviderAudit.Action.WEBHOOK_RETRY,
            actor_user=actor_user,
            metadata={"status": "error", "detail": str(exc)[:200]},
        )
        raise InvalidProviderCredentialsError(str(exc)) from exc
    PaymentProviderAudit.objects.create(
        tenant=tenant,
        provider=PROVIDER_INTER,
        action=PaymentProviderAudit.Action.WEBHOOK_RETRY,
        actor_user=actor_user,
        metadata={
            "status": "ok",
            "count": len(refs),
            "codigoSolicitacao": refs[:50],
        },
    )

    inbox_reprocessed: list[str] = []
    if reprocess_local_inbox and refs:
        from apps.billing.models import WebhookInbox
        from apps.billing.services import reprocess_webhook

        qs = WebhookInbox.objects.filter(
            tenant=tenant,
            provider=PROVIDER_INTER,
            status=WebhookInbox.Status.FAILED,
        )
        ref_set = set(refs)
        for inbox in qs.iterator():
            payload = inbox.raw_payload or {}
            gateway_ref = str(payload.get("gateway_ref") or "")
            if gateway_ref in ref_set:
                updated = reprocess_webhook(inbox)
                inbox_reprocessed.append(str(updated.id))

    return {
        "status": "ok",
        "provider": PROVIDER_INTER,
        "codigoSolicitacao": refs,
        "inbox_reprocessed": inbox_reprocessed,
        "gateway": raw if isinstance(raw, dict) else {"raw": raw},
    }
