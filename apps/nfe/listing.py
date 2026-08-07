"""Filtros de listagem NF-e (LLR UI T1 / API §8)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.nfe.models import NfeInvoice

DEFAULT_LIST_DAYS = 30


def _parse_date_param(raw: str | None) -> date | None:
    if not raw:
        return None
    d = parse_date(str(raw).strip()[:10])
    return d


def filter_invoice_queryset(
    qs: QuerySet[NfeInvoice],
    *,
    status: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    days: str | int | None = None,
    apply_default_period: bool = True,
) -> QuerySet[NfeInvoice]:
    """
    Aplica status, busca livre e janela de datas em `issue_date`.

    Default: últimos 30 dias em issue_date se nenhum from/to/days explícito
    (e se não pedir all period via days=0 ou all=1 no caller).
    """
    status_f = (status or "").strip().lower()
    if status_f and status_f != "all":
        if status_f == "processing":
            qs = qs.filter(
                status__in=[
                    NfeInvoice.Status.QUEUED,
                    NfeInvoice.Status.SUBMITTING,
                    NfeInvoice.Status.POLLING,
                    NfeInvoice.Status.CANCEL_REQUESTED,
                ]
            )
        else:
            qs = qs.filter(status=status_f)

    term = (q or "").strip()
    if term:
        digits = "".join(ch for ch in term if ch.isdigit())
        clauses = Q(idempotency_key__icontains=term) | Q(access_key__icontains=term)
        clauses |= Q(protocol__icontains=term) | Q(customer__name__icontains=term)
        clauses |= Q(customer__document__icontains=term)
        if digits:
            clauses |= Q(access_key__icontains=digits) | Q(customer__document__icontains=digits)
            if digits.isdigit() and len(digits) <= 9:
                clauses |= Q(number=int(digits))
        qs = qs.filter(clauses).distinct()

    d_from = _parse_date_param(date_from)
    d_to = _parse_date_param(date_to)
    period_explicit = bool(date_from or date_to or days is not None and str(days) != "")

    if days is not None and str(days).strip() != "":
        try:
            n = int(days)
        except (TypeError, ValueError):
            n = DEFAULT_LIST_DAYS
        if n > 0:
            start = timezone.localdate() - timedelta(days=n)
            qs = qs.filter(issue_date__gte=start)
        # n<=0 → sem filtro de período (all history)
    elif period_explicit:
        if d_from:
            qs = qs.filter(issue_date__gte=d_from)
        if d_to:
            qs = qs.filter(issue_date__lte=d_to)
    elif apply_default_period:
        start = timezone.localdate() - timedelta(days=DEFAULT_LIST_DAYS)
        qs = qs.filter(issue_date__gte=start)

    return qs


def sanitize_event_metadata(meta: Any) -> dict:
    """Remove raw SEFAZ pesado da timeline de UI."""
    if not isinstance(meta, dict):
        return {}
    out: dict = {}
    for k, v in meta.items():
        if k in {"raw", "signed_xml", "xml", "password", "pfx"}:
            if k == "raw" and isinstance(v, dict):
                out["cStat"] = v.get("cStat") or v.get("c_stat") or ""
                out["xMotivo"] = str(v.get("xMotivo") or v.get("x_motivo") or "")[:200]
                out["nRec"] = v.get("nRec") or ""
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = {sk: sv for sk, sv in v.items() if isinstance(sv, (str, int, float, bool))}
    return out
