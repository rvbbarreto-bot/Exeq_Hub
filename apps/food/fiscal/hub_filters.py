"""Filtros da fila fiscal iFood no Hub (B8)."""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q, QuerySet

from apps.food.models import FoodOrder, FoodOrderLine


def _unmapped_line_subquery():
    return FoodOrderLine.objects.filter(order_id=OuterRef("pk")).filter(
        Q(product__isnull=True) | Q(product__nfe_product__isnull=True)
    )


def filter_ifood_fiscal_orders(
    qs: QuerySet,
    *,
    fiscal_filter: str = "",
    mapping_filter: str = "",
    q: str = "",
) -> QuerySet:
    fiscal_filter = (fiscal_filter or "").strip()
    mapping_filter = (mapping_filter or "").strip()
    q = (q or "").strip()

    if fiscal_filter == "failed":
        qs = qs.filter(
            fiscal_status__in=[
                FoodOrder.FiscalStatus.REJECTED,
                FoodOrder.FiscalStatus.FAILED,
            ]
        )
    elif fiscal_filter == "pending":
        qs = qs.filter(
            fiscal_status__in=[
                "",
                FoodOrder.FiscalStatus.PENDING,
                FoodOrder.FiscalStatus.REJECTED,
                FoodOrder.FiscalStatus.FAILED,
            ]
        ).exclude(fiscal_status=FoodOrder.FiscalStatus.AUTHORIZED)
    elif fiscal_filter == "ready":
        qs = (
            qs.filter(
                fiscal_status__in=[
                    "",
                    FoodOrder.FiscalStatus.PENDING,
                    FoodOrder.FiscalStatus.REJECTED,
                    FoodOrder.FiscalStatus.FAILED,
                ]
            )
            .exclude(fiscal_status=FoodOrder.FiscalStatus.IGNORED)
            .exclude(Exists(_unmapped_line_subquery()))
        )
    elif fiscal_filter == "authorized":
        qs = qs.filter(fiscal_status=FoodOrder.FiscalStatus.AUTHORIZED)
    elif fiscal_filter == "ignored":
        qs = qs.filter(fiscal_status=FoodOrder.FiscalStatus.IGNORED)
    elif fiscal_filter == "cancelled":
        qs = qs.filter(fiscal_status=FoodOrder.FiscalStatus.CANCELLED)

    if mapping_filter == "unmapped":
        qs = qs.filter(Exists(_unmapped_line_subquery()))
    elif mapping_filter == "mapped":
        qs = qs.exclude(Exists(_unmapped_line_subquery()))

    if q:
        qs = qs.filter(channel_ref__icontains=q)

    return qs
