"""Factory de providers Food."""

from __future__ import annotations

from apps.food.payments.inter_adapter import BillingChargeFoodPaymentProvider
from apps.food.payments.mercadopago.gateway import MercadoPagoFoodPaymentProvider
from apps.food.payments.port import FoodPaymentProvider
from apps.food.payments.router import (
    BILLING_CHARGE_PROVIDERS,
    PROVIDER_MERCADOPAGO,
    resolve_food_payment_provider,
)


def get_food_payment_provider(*, tenant, provider_kind: str | None = None) -> FoodPaymentProvider:
    kind = (provider_kind or resolve_food_payment_provider(tenant=tenant)).lower().strip()
    if kind == PROVIDER_MERCADOPAGO:
        return MercadoPagoFoodPaymentProvider(kind=kind)
    if kind in BILLING_CHARGE_PROVIDERS:
        return BillingChargeFoodPaymentProvider(kind=kind)
    return BillingChargeFoodPaymentProvider(kind=kind)
