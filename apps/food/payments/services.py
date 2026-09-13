"""Orquestração de pagamentos Food."""

from __future__ import annotations

from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.registry import get_food_payment_provider
from apps.food.payments.router import resolve_food_payment_provider
from apps.food.services import mark_order_paid


def create_payment_intent_for_order(
    *,
    tenant,
    order_id,
    method: str = "pix",
    due_date=None,
    card_token: str = "",
    payment_method_id: str = "",
    issuer_id: str = "",
    installments: int = 1,
) -> FoodOrder:
    kind = resolve_food_payment_provider(tenant=tenant)
    provider = get_food_payment_provider(tenant=tenant, provider_kind=kind)
    return provider.create_payment_intent(
        tenant=tenant,
        order_id=order_id,
        method=method,
        due_date=due_date,
        card_token=card_token,
        payment_method_id=payment_method_id,
        issuer_id=issuer_id,
        installments=installments,
    )


def get_active_food_payment(order: FoodOrder) -> FoodPayment | None:
    return (
        FoodPayment.objects.filter(
            tenant_id=order.tenant_id,
            order=order,
            status__in=[
                FoodPayment.Status.PENDING,
                FoodPayment.Status.AWAITING_PAYMENT,
                FoodPayment.Status.PAID,
            ],
        )
        .order_by("-created_at")
        .first()
    )


def sync_food_order_on_payment_paid(*, tenant, payment: FoodPayment) -> FoodOrder | None:
    """Confirma pedido após FoodPayment pago (Mercado Pago / reconciliação)."""
    order = (
        FoodOrder.objects.filter(tenant=tenant, pk=payment.order_id)
        .order_by("created_at")
        .first()
    )
    if order is None:
        return None
    ref = (payment.provider_payment_id or order.pix_txid or "")[:128]
    return mark_order_paid(
        tenant=tenant,
        order_id=order.id,
        provider_ref=ref,
        deduct_stock=True,
    )


def create_order_with_auto_payment(
    *,
    tenant,
    customer_id,
    channel: str,
    lines: list,
    idempotency_key: str,
    payment_method: str = "pix",
    channel_ref: str = "",
    notes: str = "",
    **order_kwargs,
) -> FoodOrder:
    """
    Cria pedido Food e emite pagamento em uma operação (contrato WhatsApp / integradores).

    Uso previsto: integração externa ou futuro apps/channel — sem alterar billing/channel hoje.
    """
    from apps.food.services import create_order

    order = create_order(
        tenant=tenant,
        customer_id=customer_id,
        channel=channel,
        lines=lines,
        idempotency_key=idempotency_key,
        notes=notes,
        await_pix=True,
        **order_kwargs,
    )
    if channel_ref and order.channel_ref != channel_ref:
        order.channel_ref = channel_ref.strip()[:128]
        order.save(update_fields=["channel_ref", "updated_at"])
    if order.payment_status != FoodOrder.PaymentStatus.PAID:
        order = create_payment_intent_for_order(
            tenant=tenant,
            order_id=order.id,
            method=payment_method,
        )
    return order
