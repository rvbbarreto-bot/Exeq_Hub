"""De-para FoodProduct → NfeProduct (B3)."""

from __future__ import annotations

from typing import Any

from apps.food.exceptions import FoodInvalidOrderError
from apps.food.fiscal.readiness import refresh_food_order_fiscal_state
from apps.food.models import FoodOrder, FoodOrderLine, FoodProduct
from apps.nfe.models import NfeProduct

_REFRESH_FISCAL_STATUSES = frozenset(
    {
        "",
        FoodOrder.FiscalStatus.PENDING,
        FoodOrder.FiscalStatus.REJECTED,
        FoodOrder.FiscalStatus.FAILED,
    }
)


def set_food_product_nfe_mapping(
    *,
    tenant,
    product: FoodProduct,
    nfe_product_id,
) -> FoodProduct:
    if nfe_product_id:
        nfe = NfeProduct.objects.filter(
            tenant=tenant, pk=nfe_product_id, is_active=True
        ).first()
        if nfe is None:
            raise FoodInvalidOrderError("Produto fiscal não encontrado ou inativo.")
        product.nfe_product = nfe
    else:
        product.nfe_product = None
    product.save(update_fields=["nfe_product", "updated_at"])
    refresh_ifood_orders_for_food_product(tenant=tenant, product=product)
    return product


def refresh_ifood_orders_for_food_product(*, tenant, product: FoodProduct) -> int:
    order_ids = (
        FoodOrderLine.objects.filter(
            tenant=tenant,
            product=product,
            order__channel=FoodOrder.Channel.IFOOD,
            order__fiscal_status__in=_REFRESH_FISCAL_STATUSES,
        )
        .values_list("order_id", flat=True)
        .distinct()
    )
    updated = 0
    for oid in order_ids:
        order = FoodOrder.objects.filter(tenant=tenant, pk=oid).first()
        if order is None:
            continue
        refresh_food_order_fiscal_state(order)
        updated += 1
    return updated


def order_lines_mapping_summary(order: FoodOrder) -> dict[str, Any]:
    unmapped: list[str] = []
    for line in order.lines.select_related("product", "product__nfe_product"):
        if line.product is None or line.product.nfe_product_id is None:
            unmapped.append(line.sku)
    return {
        "all_mapped": not unmapped,
        "unmapped_skus": unmapped,
        "line_count": order.lines.count(),
    }


def is_food_order_fiscally_ready(order: FoodOrder) -> bool:
    if order.channel != FoodOrder.Channel.IFOOD:
        return False
    summary = order_lines_mapping_summary(order)
    if not summary["all_mapped"]:
        return False
    warnings = order.fiscal_warnings or []
    for w in warnings:
        if w.get("level") == "error":
            return False
    return True
