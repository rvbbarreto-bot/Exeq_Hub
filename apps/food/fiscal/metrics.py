"""KPIs piloto iFood fiscal (B10 / go-live)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.food.models import FoodFiscalEvent, FoodOrder


def compute_ifood_fiscal_piloto_kpis(
    *,
    tenant_id,
    since=None,
) -> dict[str, Any]:
    since = since or (timezone.now() - timedelta(days=7))
    base = FoodOrder.objects.filter(
        tenant_id=tenant_id,
        channel=FoodOrder.Channel.IFOOD,
        created_at__gte=since,
    )
    fiscal_counts: dict[str, int] = {"empty": base.filter(fiscal_status="").count()}
    for code, _label in FoodOrder.FiscalStatus.choices:
        if code:
            fiscal_counts[code] = base.filter(fiscal_status=code).count()

    events = FoodFiscalEvent.objects.filter(
        tenant_id=tenant_id,
        occurred_at__gte=since,
    )
    return {
        "since": since.isoformat(),
        "orders_imported": base.count(),
        "fiscal_by_status": fiscal_counts,
        "authorized": base.filter(fiscal_status=FoodOrder.FiscalStatus.AUTHORIZED).count(),
        "failed_or_rejected": base.filter(
            fiscal_status__in=[
                FoodOrder.FiscalStatus.FAILED,
                FoodOrder.FiscalStatus.REJECTED,
            ]
        ).count(),
        "ignored": base.filter(fiscal_status=FoodOrder.FiscalStatus.IGNORED).count(),
        "audit_events": events.count(),
        "emit_done_events": events.filter(
            action=FoodFiscalEvent.Action.EMIT_DONE
        ).count(),
    }
