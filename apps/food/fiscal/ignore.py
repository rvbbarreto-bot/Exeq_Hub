"""Ignorar pedido iFood para emissão fiscal (B7 / HP-06)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.food.exceptions import FoodInvalidOrderError, FoodOrderNotFoundError
from apps.food.fiscal.readiness import refresh_food_order_fiscal_state
from apps.food.models import FoodFiscalEvent, FoodOrder


def clear_food_order_fiscal_ignore(order: FoodOrder) -> None:
    order.fiscal_ignored_at = None
    order.fiscal_ignored_reason = ""


@transaction.atomic
def ignore_food_order_fiscal(
    *,
    tenant,
    order_id,
    reason: str,
    actor: str = "api",
) -> FoodOrder:
    reason = (reason or "").strip()
    if not reason:
        raise FoodInvalidOrderError("Motivo do ignore é obrigatório.")

    order = (
        FoodOrder.objects.select_for_update()
        .filter(tenant=tenant, pk=order_id)
        .first()
    )
    if order is None:
        raise FoodOrderNotFoundError("Pedido não encontrado.")

    from_status = order.fiscal_status or ""

    if order.channel != FoodOrder.Channel.IFOOD:
        raise FoodInvalidOrderError("Ignore fiscal só para pedidos iFood.")

    if order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED:
        raise FoodInvalidOrderError("Pedido já possui NFC-e autorizada.")

    if order.fiscal_status == FoodOrder.FiscalStatus.PROCESSING:
        raise FoodInvalidOrderError("Emissão fiscal em andamento.")

    order.fiscal_status = FoodOrder.FiscalStatus.IGNORED
    order.fiscal_ignored_at = timezone.now()
    order.fiscal_ignored_reason = reason[:255]
    order.fiscal_rejection_code = ""
    order.fiscal_rejection_message = ""
    order.save(
        update_fields=[
            "fiscal_status",
            "fiscal_ignored_at",
            "fiscal_ignored_reason",
            "fiscal_rejection_code",
            "fiscal_rejection_message",
            "updated_at",
        ]
    )
    refresh_food_order_fiscal_state(order)
    from apps.food.fiscal.observability import audit_food_fiscal

    audit_food_fiscal(
        tenant=tenant,
        order=order,
        action=FoodFiscalEvent.Action.IGNORE,
        actor=actor,
        from_status=from_status,
        metadata={"reason_len": len(reason)},
    )
    return order


def prepare_ignored_order_for_reemit(order: FoodOrder) -> None:
    """PO: reemitir direto — limpa ignore e incrementa tentativa."""
    clear_food_order_fiscal_ignore(order)
    order.fiscal_emit_attempt = int(order.fiscal_emit_attempt or 0) + 1
    order.fiscal_status = FoodOrder.FiscalStatus.PENDING
    order.save(
        update_fields=[
            "fiscal_status",
            "fiscal_ignored_at",
            "fiscal_ignored_reason",
            "fiscal_emit_attempt",
            "updated_at",
        ]
    )
