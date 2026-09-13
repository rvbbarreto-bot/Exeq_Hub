"""Processamento de webhooks Mercado Pago (Food)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.food.exceptions import (
    FoodInvalidOrderError,
    FoodPaymentError,
    FoodPaymentProviderError,
)
from apps.food.models import FoodPayment, FoodPaymentEvent
from apps.food.payments.mercadopago.client import MercadoPagoClient
from apps.food.payments.mercadopago.normalize import (
    extract_event_id,
    extract_payment_id,
    map_mp_status,
    payment_amount_cents,
)
from apps.food.payments.mercadopago.webhook_security import (
    get_webhook_secret,
    verify_mercadopago_signature,
)
from apps.food.payments.router import PROVIDER_MERCADOPAGO
from apps.food.payments.services import sync_food_order_on_payment_paid

logger = logging.getLogger(__name__)


class InvalidFoodWebhookSignatureError(FoodPaymentError):
    code = "food_webhook_invalid_signature"


class FoodPaymentNotFoundError(FoodPaymentError):
    code = "food_payment_not_found"


def _find_payment(*, payment_id: str) -> FoodPayment | None:
    pid = (payment_id or "").strip()
    if not pid:
        return None
    matches = list(
        FoodPayment.objects.filter(
            provider=PROVIDER_MERCADOPAGO,
            provider_payment_id=pid,
        )
        .select_related("tenant", "order")
        .order_by("created_at")[:2]
    )
    if len(matches) > 1:
        tenants = {m.tenant_id for m in matches}
        if len(tenants) > 1:
            raise FoodPaymentNotFoundError(
                "provider_payment_id ambíguo entre tenants — reconciliar manualmente"
            )
    return matches[0] if matches else None


def _apply_payment_status(
    *,
    payment: FoodPayment,
    mp_data: dict[str, Any],
) -> FoodPayment:
    hub_status = map_mp_status(str(mp_data.get("status") or ""))
    status_detail = str(mp_data.get("status_detail") or "")[:255]
    status_map = {
        "paid": FoodPayment.Status.PAID,
        "failed": FoodPayment.Status.FAILED,
        "cancelled": FoodPayment.Status.CANCELLED,
        "expired": FoodPayment.Status.EXPIRED,
        "awaiting_payment": FoodPayment.Status.AWAITING_PAYMENT,
    }
    new_status = status_map.get(hub_status, FoodPayment.Status.AWAITING_PAYMENT)

    if payment.status == FoodPayment.Status.PAID and new_status == FoodPayment.Status.PAID:
        return payment

    amount = payment_amount_cents(mp_data)
    if amount is not None and amount != payment.amount_cents and new_status == FoodPayment.Status.PAID:
        raise FoodInvalidOrderError(
            f"Valor Mercado Pago ({amount}) diverge do pedido ({payment.amount_cents})."
        )

    payment.status = new_status
    payment.failure_detail = status_detail if new_status == FoodPayment.Status.FAILED else ""
    payment.gateway_payload = mp_data
    if new_status == FoodPayment.Status.PAID:
        payment.paid_at = timezone.now()
    payment.save(
        update_fields=[
            "status",
            "failure_detail",
            "gateway_payload",
            "paid_at",
            "updated_at",
        ]
    )
    return payment


@transaction.atomic
def ingest_mercadopago_webhook(
    *,
    raw_body: bytes,
    payload: dict[str, Any],
    x_signature: str = "",
    x_request_id: str = "",
    query_params: dict[str, str] | None = None,
) -> FoodPaymentEvent:
    payment_id = extract_payment_id(payload=payload, query_params=query_params)
    if not payment_id:
        raise FoodPaymentNotFoundError("payment id ausente na notificação Mercado Pago")

    payment = _find_payment(payment_id=payment_id)
    if payment is None:
        raise FoodPaymentNotFoundError(
            f"FoodPayment não encontrado para provider_payment_id={payment_id}"
        )

    secret = get_webhook_secret(tenant=payment.tenant)
    if secret and not verify_mercadopago_signature(
        secret=secret,
        x_signature=x_signature,
        x_request_id=x_request_id,
        data_id=payment_id,
    ):
        raise InvalidFoodWebhookSignatureError("Assinatura Mercado Pago inválida")

    event_id = extract_event_id(payload=payload, x_request_id=x_request_id)
    existing = FoodPaymentEvent.objects.filter(
        tenant=payment.tenant,
        provider=PROVIDER_MERCADOPAGO,
        event_id=event_id,
    ).first()
    if existing is not None:
        return existing

    client = MercadoPagoClient(tenant=payment.tenant)
    mp_data = _resolve_payment_payload(
        client=client,
        payment=payment,
        payment_id=payment_id,
        payload=payload,
    )

    try:
        event = FoodPaymentEvent.objects.create(
            tenant=payment.tenant,
            payment=payment,
            provider=PROVIDER_MERCADOPAGO,
            event_id=event_id,
            payload={"notification": payload, "payment": mp_data},
        )
    except IntegrityError:
        return FoodPaymentEvent.objects.get(
            tenant=payment.tenant,
            provider=PROVIDER_MERCADOPAGO,
            event_id=event_id,
        )

    payment = (
        FoodPayment.objects.select_for_update()
        .select_related("order", "tenant")
        .get(pk=payment.pk)
    )
    payment = _apply_payment_status(payment=payment, mp_data=mp_data)

    if payment.status == FoodPayment.Status.PAID:
        sync_food_order_on_payment_paid(tenant=payment.tenant, payment=payment)

    return event


def _resolve_payment_payload(
    *,
    client: MercadoPagoClient,
    payment: FoodPayment,
    payment_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    embedded = payload.get("payment")
    if isinstance(embedded, dict) and embedded.get("id") is not None:
        return embedded
    if client.mode != "http":
        status = str(payload.get("mp_status") or "").strip()
        if not status:
            simulate = payload.get("simulate_approved", True)
            status = "approved" if simulate else "pending"
        return client.stub_payment_detail(
            payment_id=payment_id,
            status=status,
            amount_cents=payment.amount_cents,
        )
    return client.get_payment(payment_id=payment_id)
