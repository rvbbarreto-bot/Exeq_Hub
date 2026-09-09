"""Contexto Hub — painel fiscal iFood (B8)."""

from __future__ import annotations

from typing import Any

from apps.food.fiscal.mapping import is_food_order_fiscally_ready, order_lines_mapping_summary
from apps.food.models import FoodOrder
from apps.nfce.models import NfceInvoice


def food_order_fiscal_panel_context(order: FoodOrder) -> dict[str, Any]:
    if order.channel != FoodOrder.Channel.IFOOD:
        return {"fiscal_is_ifood": False}

    mapping = order_lines_mapping_summary(order)
    nfce = getattr(order, "nfce_invoice", None)
    fs = order.fiscal_status
    can_emit = fs not in {
        FoodOrder.FiscalStatus.AUTHORIZED,
        FoodOrder.FiscalStatus.PROCESSING,
    }
    can_cancel = (
        nfce is not None and nfce.status == NfceInvoice.Status.AUTHORIZED
    )
    return {
        "fiscal_is_ifood": True,
        "fiscal_mapping": mapping,
        "fiscal_ready": is_food_order_fiscally_ready(order),
        "fiscal_can_emit": can_emit,
        "fiscal_can_ignore": can_emit,
        "fiscal_can_cancel_nfce": can_cancel,
        "fiscal_logistic_cancelled": (
            order.status == FoodOrder.Status.CANCELLED
            and fs == FoodOrder.FiscalStatus.AUTHORIZED
        ),
    }
