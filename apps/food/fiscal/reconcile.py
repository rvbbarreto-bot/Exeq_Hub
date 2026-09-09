"""Reconcile pedidos iFood presos em PROCESSING (D6 / EX-EMT-05)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.food.fiscal.nfce_sync import sync_food_orders_from_nfce_invoice
from apps.food.fiscal.readiness import refresh_food_order_fiscal_state
from apps.food.models import FoodOrder
from apps.nfce.models import NfceInvoice

logger = logging.getLogger(__name__)


def reconcile_stale_seconds() -> int:
    return max(
        60,
        int(getattr(settings, "FOOD_FISCAL_RECONCILE_STALE_SECONDS", 900) or 900),
    )


def reconcile_stale_food_fiscal_processing(*, limit: int = 50) -> dict[str, int]:
    cutoff = timezone.now() - timedelta(seconds=reconcile_stale_seconds())
    qs = FoodOrder.objects.filter(
        channel=FoodOrder.Channel.IFOOD,
        fiscal_status=FoodOrder.FiscalStatus.PROCESSING,
        updated_at__lte=cutoff,
    ).select_related("nfce_invoice")[:limit]

    stats = {"checked": 0, "synced": 0, "polled": 0, "reset_failed": 0}
    for order in qs:
        stats["checked"] += 1
        inv = order.nfce_invoice
        if inv is None:
            order.fiscal_status = FoodOrder.FiscalStatus.FAILED
            order.fiscal_rejection_code = "reconcile_orphan"
            order.fiscal_rejection_message = "Emissão interrompida sem NFC-e vinculada."
            order.save(
                update_fields=[
                    "fiscal_status",
                    "fiscal_rejection_code",
                    "fiscal_rejection_message",
                    "updated_at",
                ]
            )
            refresh_food_order_fiscal_state(order)
            stats["reset_failed"] += 1
            continue

        if inv.status in {
            NfceInvoice.Status.POLLING,
            NfceInvoice.Status.SUBMITTING,
        }:
            try:
                from apps.nfce.polling import poll_nfce_invoice

                poll_nfce_invoice(inv, actor="food_reconcile")
                inv.refresh_from_db()
                stats["polled"] += 1
            except Exception:
                logger.exception("food.reconcile_poll_failed order=%s invoice=%s", order.id, inv.id)

        stats["synced"] += sync_food_orders_from_nfce_invoice(inv)
        order.refresh_from_db()
        if order.fiscal_status == FoodOrder.FiscalStatus.PROCESSING:
            order.fiscal_status = FoodOrder.FiscalStatus.FAILED
            order.fiscal_rejection_code = "reconcile_stale"
            order.fiscal_rejection_message = "Processamento fiscal expirou (TTL reconcile)."
            order.save(
                update_fields=[
                    "fiscal_status",
                    "fiscal_rejection_code",
                    "fiscal_rejection_message",
                    "updated_at",
                ]
            )
            refresh_food_order_fiscal_state(order)
            stats["reset_failed"] += 1

    from apps.food.fiscal.observability import log_fiscal_event

    log_fiscal_event(
        "reconcile_done",
        tenant_id="-",
        actor="food_reconcile",
        **stats,
    )
    return stats
