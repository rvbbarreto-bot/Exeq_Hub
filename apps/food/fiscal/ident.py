"""Helpers identificação consumidor iFood → NFC-e."""

from __future__ import annotations

from apps.food.models import FoodOrder


def resolve_food_order_customer_ident(order: FoodOrder) -> tuple[str | None, str | None]:
    doc = "".join(ch for ch in (order.customer.document or "") if ch.isdigit())
    if len(doc) == 11:
        return doc, None
    if len(doc) == 14:
        return None, doc
    return None, None
