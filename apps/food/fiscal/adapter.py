"""Adapter FoodOrder → payload NFC-e."""

from __future__ import annotations

from typing import Any

from apps.food.exceptions import FoodInvalidOrderError
from apps.food.models import FoodOrder


def build_nfce_items_from_food_order(order: FoodOrder) -> list[dict[str, Any]]:
    if order.channel != FoodOrder.Channel.IFOOD:
        raise FoodInvalidOrderError("Emissão fiscal iFood só para canal ifood.")

    items: list[dict[str, Any]] = []
    for line in order.lines.select_related("product", "product__nfe_product"):
        product = line.product
        if product is None or product.nfe_product_id is None:
            raise FoodInvalidOrderError(
                f"SKU {line.sku} sem produto fiscal mapeado (nfe_product)."
            )
        items.append(
            {
                "product_id": str(product.nfe_product_id),
                "quantity": str(line.quantity),
                "unit_price_cents": line.unit_price_cents,
            }
        )
    if not items:
        raise FoodInvalidOrderError("Pedido sem itens para NFC-e.")
    return items


def food_order_delivery_flag(order: FoodOrder) -> bool:
    return order.fulfillment_mode == FoodOrder.FulfillmentMode.DELIVERY
