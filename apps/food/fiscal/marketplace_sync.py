"""Sync logístico marketplace → FoodOrder (B1). Fiscal separado (PO-3)."""

from __future__ import annotations

from typing import Any

from apps.food.exceptions import FoodInvalidTransitionError
from apps.food.fiscal.readiness import refresh_food_order_fiscal_state
from apps.food.models import FoodOrder
from apps.food.operations import ORDER_TRANSITIONS, transition_order_status


def _marketplace_idempotency_key(*, provider: str, external_order_id: str) -> str:
    return f"mp:{provider}:{external_order_id}"


def find_marketplace_order(*, tenant, provider: str, external_order_id: str) -> FoodOrder | None:
    ext = (external_order_id or "").strip()
    if not ext:
        return None
    return FoodOrder.objects.filter(
        tenant=tenant,
        idempotency_key=_marketplace_idempotency_key(provider=provider, external_order_id=ext),
    ).first()


def cancel_marketplace_order_logistic(*, tenant, order: FoodOrder) -> FoodOrder:
    """
    Cancela somente status logístico. NFC-e AUTHORIZED permanece (PO-3).
    """
    if order.status == FoodOrder.Status.CANCELLED:
        return order

    allowed = ORDER_TRANSITIONS.get(order.status, set())
    if FoodOrder.Status.CANCELLED in allowed:
        try:
            return transition_order_status(
                tenant=tenant,
                order_id=order.id,
                to_status=FoodOrder.Status.CANCELLED,
            )
        except FoodInvalidTransitionError:
            pass

    order.status = FoodOrder.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    if order.channel == FoodOrder.Channel.IFOOD:
        refresh_food_order_fiscal_state(order)
    return order


def apply_marketplace_logistic_sync(
    *,
    tenant,
    provider: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Aplica evento de cancelamento (polling). Retorna metadados da operação.

    EX-ING-07: cancel pré-emissão → logístico cancelled, fiscal intacto.
    EX-ING-08: cancel pós-AUTHORIZED → aviso fiscal, sem auto-cancel NFC-e.
    """
    ext = str(payload.get("external_order_id") or "").strip()
    if not ext:
        return {"action": "error", "code": "missing_external_order_id"}

    order = find_marketplace_order(tenant=tenant, provider=provider, external_order_id=ext)
    if order is None:
        return {"action": "skipped", "code": "order_not_found", "external_order_id": ext}

    if not payload.get("cancelled"):
        return {
            "action": "skipped",
            "code": "not_cancelled",
            "order_id": str(order.id),
        }

    prev_status = order.status
    prev_fiscal = order.fiscal_status
    order = cancel_marketplace_order_logistic(tenant=tenant, order=order)
    order.refresh_from_db()

    out: dict[str, Any] = {
        "action": "cancelled",
        "order_id": str(order.id),
        "external_order_id": ext,
        "logistic_status": order.status,
        "fiscal_status": order.fiscal_status or FoodOrder.FiscalStatus.PENDING,
        "previous_logistic_status": prev_status,
        "previous_fiscal_status": prev_fiscal,
    }
    if (
        order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
        and order.status == FoodOrder.Status.CANCELLED
    ):
        warnings = order.fiscal_warnings or []
        codes = {w.get("code") for w in warnings}
        out["fiscal_warning"] = "marketplace_cancelled_with_nfce"
        out["requires_manual_nfce_cancel"] = "marketplace_cancelled_with_nfce" in codes
    return out
