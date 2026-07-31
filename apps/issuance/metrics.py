"""KPIs mínimos do piloto NFS-e (Plano §15 / M5) — ORM + logs, sem Prometheus."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import DigitalCertificate
from apps.issuance.models import NfIssue, NfIssueEvent


def compute_nfse_piloto_kpis(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    tenant_id=None,
) -> dict[str, Any]:
    """Agrega taxas a partir de NfIssue / eventos / certificados."""
    now = timezone.now()
    since = since or (now - timedelta(days=30))
    until = until or now

    qs = NfIssue.objects.filter(created_at__gte=since, created_at__lte=until)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)

    by_status = {
        row["status"]: row["c"]
        for row in qs.values("status").annotate(c=Count("id"))
    }
    total = sum(by_status.values()) or 0
    authorized = by_status.get(NfIssue.Status.AUTHORIZED, 0) + by_status.get(
        NfIssue.Status.CANCELLED, 0
    )
    rejected = by_status.get(NfIssue.Status.REJECTED, 0)
    submitted = total - by_status.get(NfIssue.Status.DRAFT, 0)

    auth_qs = qs.filter(
        status__in={NfIssue.Status.AUTHORIZED, NfIssue.Status.CANCELLED}
    )
    auth_n = auth_qs.count()
    happy = auth_qs.exclude(
        id__in=NfIssueEvent.objects.filter(
            to_status=NfIssue.Status.POLLING
        ).values("nf_issue_id")
    ).count()

    certs = DigitalCertificate.objects.exclude(
        status=DigitalCertificate.Status.REVOKED,
    )
    if tenant_id is not None:
        certs = certs.filter(tenant_id=tenant_id)
    expiring = certs.filter(
        status__in={
            DigitalCertificate.Status.EXPIRING,
            DigitalCertificate.Status.EXPIRED,
        }
    ).count()

    def _rate(n: int, d: int) -> float | None:
        if d <= 0:
            return None
        return round(n / d, 4)

    return {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "total_issues": total,
        "by_status": {str(k): v for k, v in by_status.items()},
        "authorization_rate": _rate(authorized, submitted or total),
        "rejection_rate": _rate(rejected, submitted or total),
        "happy_path_no_poll_rate": _rate(happy, auth_n),
        "authorized_or_cancelled": auth_n,
        "happy_path_count": happy,
        "certificates_expiring_or_expired": expiring,
        "notes": {
            "pdf_p95": "ver logs nfse.pdf_ms (instrumentação runtime)",
            "plano": "Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md §15",
        },
    }
