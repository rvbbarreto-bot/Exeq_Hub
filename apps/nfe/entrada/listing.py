"""Filtros e KPIs — listagem NF-e de entrada (Hub V4 / API)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.nfe.entrada.models import NfeEntradaDocument

DEFAULT_LIST_DAYS = 30


def _parse_date_param(raw: str | None) -> date | None:
    if not raw:
        return None
    return parse_date(str(raw).strip()[:10])


def filter_entrada_queryset(
    qs: QuerySet[NfeEntradaDocument],
    *,
    q: str | None = None,
    manifest_status: str | None = None,
    xml_status: str | None = None,
    provider_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    days: str | int | None = None,
    apply_default_period: bool = True,
) -> QuerySet[NfeEntradaDocument]:
    manifest_f = (manifest_status or "").strip().lower()
    if manifest_f and manifest_f != "all":
        qs = qs.filter(manifest_status=manifest_f)

    xml_f = (xml_status or "").strip().lower()
    if xml_f and xml_f != "all":
        qs = qs.filter(xml_status=xml_f)

    pid = (provider_id or "").strip()
    if pid:
        qs = qs.filter(provider_id=pid)

    term = (q or "").strip()
    if term:
        digits = "".join(ch for ch in term if ch.isdigit())
        clauses = (
            Q(issuer_name__icontains=term)
            | Q(access_key__icontains=term)
            | Q(issuer_cnpj__icontains=term)
        )
        if digits:
            clauses |= Q(access_key__icontains=digits) | Q(issuer_cnpj__icontains=digits)
            if digits.isdigit() and len(digits) <= 9:
                clauses |= Q(number=int(digits))
        qs = qs.filter(clauses)

    d_from = _parse_date_param(date_from)
    d_to = _parse_date_param(date_to)
    if d_from:
        qs = qs.filter(issue_date__gte=d_from)
    if d_to:
        qs = qs.filter(issue_date__lte=d_to)

    if apply_default_period and not d_from and not d_to and days in (None, ""):
        cutoff = timezone.localdate() - timedelta(days=DEFAULT_LIST_DAYS)
        qs = qs.filter(Q(issue_date__gte=cutoff) | Q(issue_date__isnull=True))

    if days not in (None, ""):
        try:
            n_days = int(days)
        except (TypeError, ValueError):
            n_days = DEFAULT_LIST_DAYS
        if n_days > 0:
            cutoff = timezone.localdate() - timedelta(days=n_days)
            qs = qs.filter(Q(issue_date__gte=cutoff) | Q(issue_date__isnull=True))
        elif n_days == 0:
            pass

    return qs


def compute_entrada_kpis(qs: QuerySet[NfeEntradaDocument]) -> dict[str, Any]:
    agg = qs.aggregate(
        total=Count("id"),
        xml_pending=Count("id", filter=Q(xml_status=NfeEntradaDocument.XmlStatus.PENDING)),
        manifest_pending=Count(
            "id",
            filter=Q(manifest_status=NfeEntradaDocument.ManifestStatus.NONE),
        ),
        xml_available=Count(
            "id",
            filter=Q(xml_status=NfeEntradaDocument.XmlStatus.AVAILABLE),
        ),
    )
    return {
        "total": int(agg["total"] or 0),
        "xml_pending": int(agg["xml_pending"] or 0),
        "manifest_pending": int(agg["manifest_pending"] or 0),
        "xml_available": int(agg["xml_available"] or 0),
    }
