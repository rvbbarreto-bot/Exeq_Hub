"""Seleção do provider de pagamento Food (independente do billing recorrente)."""

from __future__ import annotations

PROVIDER_INTER = "inter"
PROVIDER_ASAAS = "asaas"
PROVIDER_C6 = "c6"
PROVIDER_MERCADOPAGO = "mercadopago"

KNOWN_FOOD_PAYMENT_PROVIDERS = frozenset(
    {
        PROVIDER_INTER,
        PROVIDER_ASAAS,
        PROVIDER_C6,
        PROVIDER_MERCADOPAGO,
    }
)

BILLING_CHARGE_PROVIDERS = frozenset(
    {PROVIDER_INTER, PROVIDER_ASAAS, PROVIDER_C6}
)


def resolve_food_payment_provider(*, tenant) -> str:
    """
    Ordem:
    1. tenant.settings.food_payment_provider
    2. inter (comportamento legado)
    """
    settings_map = getattr(tenant, "settings", None) or {}
    kind = str(settings_map.get("food_payment_provider") or PROVIDER_INTER).lower().strip()
    if kind not in KNOWN_FOOD_PAYMENT_PROVIDERS:
        return PROVIDER_INTER
    return kind


def food_payment_methods_enabled(*, tenant) -> list[str]:
    settings_map = getattr(tenant, "settings", None) or {}
    raw = settings_map.get("food_payment_methods_enabled")
    if isinstance(raw, list) and raw:
        return [str(m).lower().strip() for m in raw if str(m).strip()]
    if resolve_food_payment_provider(tenant=tenant) == PROVIDER_MERCADOPAGO:
        return ["pix", "card"]
    return ["pix"]
