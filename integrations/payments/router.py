"""Seleção do provider de pagamento (multi-gateway)."""

from __future__ import annotations

from django.conf import settings

PROVIDER_ASAAS = "asaas"
PROVIDER_INTER = "inter"
PROVIDER_C6 = "c6"

KNOWN_PAYMENT_PROVIDERS = frozenset(
    {PROVIDER_ASAAS, PROVIDER_INTER, PROVIDER_C6}
)


def resolve_payment_provider_kind(
    *,
    tenant=None,
    tenant_settings: dict | None = None,
    provider_kind: str | None = None,
) -> str:
    """
    Ordem:
    1. override explícito
    2. tenant.settings.payment_provider
    3. PAYMENT_DEFAULT_PROVIDER (default inter)
    """
    if provider_kind:
        kind = str(provider_kind).lower().strip()
    else:
        settings_map = tenant_settings
        if settings_map is None and tenant is not None:
            settings_map = getattr(tenant, "settings", None) or {}
        settings_map = settings_map or {}
        kind = str(
            settings_map.get("payment_provider")
            or getattr(settings, "PAYMENT_DEFAULT_PROVIDER", PROVIDER_INTER)
            or PROVIDER_INTER
        ).lower().strip()

    if kind not in KNOWN_PAYMENT_PROVIDERS:
        return PROVIDER_INTER
    return kind
