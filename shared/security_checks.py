"""Checagens de segurança em runtime (produção / FORCE_SECURE_SECRETS)."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

# Valores conhecidos de exemplos / commits — nunca aceitar em produção.
WEAK_WEBHOOK_SECRETS = frozenset(
    {
        "",
        "dev-webhook-secret",
        "change-me",
        "secret",
        "webhook-secret",
    }
)
WEAK_FIELD_ENCRYPTION_KEYS = frozenset(
    {
        "",
        "n_AQ8FIJHEVdMys3lkm17BygqS8UkBCEfRtzlNaZhhw=",
    }
)


def assert_secure_runtime_settings() -> None:
    """
    Fail-closed: em DEBUG=False (ou FORCE_SECURE_SECRETS=true) rejeita segredos fracos.

    Alinha ao estudo Inter §9.2: HMAC do Hub só é seguro com segredo forte + proxy.
    """
    from django.conf import settings

    force = getattr(settings, "FORCE_SECURE_SECRETS", False)
    if settings.DEBUG and not force:
        return

    wh = (getattr(settings, "WEBHOOK_GATEWAY_SECRET", None) or "").strip()
    if wh in WEAK_WEBHOOK_SECRETS or len(wh) < 32:
        raise ImproperlyConfigured(
            "WEBHOOK_GATEWAY_SECRET inseguro: use segredo aleatório com ≥32 caracteres "
            "(não use o valor de .env.example)."
        )

    fe = (getattr(settings, "FIELD_ENCRYPTION_KEY", None) or "").strip()
    if fe in WEAK_FIELD_ENCRYPTION_KEYS:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY inseguro: gere uma chave Fernet própria e rotacione "
            "segredos de tenant (não use a chave de exemplo do repositório)."
        )
