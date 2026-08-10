"""RF-91 — métricas operacionais NF-e (agregados por tenant)."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from apps.nfe.models import NfeInvoice


def compute_nfe_ops_metrics(*, tenant, days: int = 30) -> dict[str, Any]:
    """Authorize rate, contagem por status, rejeições por cStat, fila polling/pdf."""
    window = max(1, min(366, int(days or 30)))
    since = timezone.now() - timedelta(days=window)
    base = NfeInvoice.objects.filter(tenant=tenant, created_at__gte=since)

    by_status = {
        row["status"]: row["c"]
        for row in base.values("status").annotate(c=Count("id"))
    }
    total = sum(by_status.values())
    authorized = by_status.get(NfeInvoice.Status.AUTHORIZED, 0)
    rejected = by_status.get(NfeInvoice.Status.REJECTED, 0)
    failed = by_status.get(NfeInvoice.Status.FAILED, 0)
    terminal = authorized + rejected + failed
    authorize_rate = (authorized / terminal) if terminal else None

    reject_codes = Counter(
        base.filter(status=NfeInvoice.Status.REJECTED)
        .exclude(rejection_code="")
        .values_list("rejection_code", flat=True)
    )
    poll_exhausted = base.filter(
        status=NfeInvoice.Status.FAILED, rejection_code="POLL_EXHAUSTED"
    ).count()
    polling_now = NfeInvoice.objects.filter(
        tenant=tenant, status=NfeInvoice.Status.POLLING
    ).count()
    pdf_pending = (
        NfeInvoice.objects.filter(
            tenant=tenant, status=NfeInvoice.Status.AUTHORIZED
        )
        .filter(last_validation__pdf_pending=True)
        .count()
    )

    return {
        "days": window,
        "since": since.isoformat(),
        "total": total,
        "by_status": by_status,
        "authorize_rate": authorize_rate,
        "rejected_by_cstat": dict(reject_codes.most_common(20)),
        "poll_exhausted": poll_exhausted,
        "polling_queue": polling_now,
        "pdf_pending": pdf_pending,
    }
