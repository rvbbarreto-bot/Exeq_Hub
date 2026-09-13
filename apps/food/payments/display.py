"""Contexto de UI para painel de pagamento Food (Hub)."""

from __future__ import annotations

from apps.food.models import FoodOrder
from apps.food.payments.mercadopago.client import get_public_key, resolve_mp_http_mode
from apps.food.payments.router import (
    PROVIDER_ASAAS,
    PROVIDER_C6,
    PROVIDER_INTER,
    PROVIDER_MERCADOPAGO,
    food_payment_methods_enabled,
    resolve_food_payment_provider,
)
from apps.food.payments.services import get_active_food_payment

PROVIDER_LABELS = {
    PROVIDER_INTER: "Inter (BolePix)",
    PROVIDER_ASAAS: "Asaas",
    PROVIDER_C6: "C6 Bank",
    PROVIDER_MERCADOPAGO: "Mercado Pago",
}


def payment_panel_context(*, tenant, order: FoodOrder) -> dict:
    provider = resolve_food_payment_provider(tenant=tenant)
    food_payment = get_active_food_payment(order)

    pix_copy_paste = ""
    payment_ref = ""
    payment_status = ""
    payment_method = ""
    payment_source = ""

    if food_payment is not None:
        pix_copy_paste = food_payment.pix_copy_paste or ""
        payment_ref = food_payment.provider_payment_id or str(food_payment.id)
        payment_status = food_payment.status
        payment_method = food_payment.method
        payment_source = "food_payment"
    elif order.charge_id and order.charge is not None:
        pix_copy_paste = order.charge.pix_copy_paste or ""
        payment_ref = order.charge.gateway_ref or str(order.charge_id)
        payment_status = order.charge.status
        payment_method = "pix"
        payment_source = "billing_charge"

    has_intent = food_payment is not None or bool(order.charge_id)
    is_paid = order.payment_status == FoodOrder.PaymentStatus.PAID
    mp_email_missing = (
        provider == PROVIDER_MERCADOPAGO
        and not (order.customer.email or "").strip()
    )
    methods_enabled = food_payment_methods_enabled(tenant=tenant)
    mp_public_key = get_public_key(tenant=tenant) if provider == PROVIDER_MERCADOPAGO else ""
    mp_stub_mode = resolve_mp_http_mode() != "http"

    return {
        "food_payment_provider": provider,
        "food_payment_provider_label": PROVIDER_LABELS.get(provider, provider),
        "food_payment": food_payment,
        "pix_copy_paste": pix_copy_paste,
        "payment_ref": payment_ref,
        "payment_status": payment_status,
        "payment_method": payment_method,
        "payment_source": payment_source,
        "has_payment_intent": has_intent,
        "can_generate_payment": not is_paid and not has_intent,
        "mp_email_missing": mp_email_missing,
        "mp_card_enabled": provider == PROVIDER_MERCADOPAGO and "card" in methods_enabled,
        "mp_pix_enabled": provider == PROVIDER_MERCADOPAGO and "pix" in methods_enabled,
        "mp_public_key": mp_public_key,
        "mp_stub_mode": mp_stub_mode,
        "payer_email": (order.customer.email or "").strip(),
        "payer_document": (order.customer.document or "").strip(),
        "payer_name": order.customer.name,
    }
