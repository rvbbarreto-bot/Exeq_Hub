"""Export pacote contábil NF-e autorizadas por competência (ACC-01)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from apps.nfe.models import NfeInvoice


def export_competence_package(
    *,
    tenant_id,
    year: int,
    month: int,
    out_dir: Path,
) -> dict[str, Any]:
    """
    Exporta JSON manifest + referências XML/PDF por NF-e autorizada/cancelada
    no mês de emissão (issue_date).
    """
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    qs = (
        NfeInvoice.objects.filter(
            tenant_id=tenant_id,
            issue_date__gte=start,
            issue_date__lt=end,
            status__in=[
                NfeInvoice.Status.AUTHORIZED,
                NfeInvoice.Status.CANCELLED,
            ],
        )
        .order_by("issue_date", "number")
        .select_related("provider", "customer")
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for inv in qs:
        snap = inv.fiscal_snapshot if isinstance(inv.fiscal_snapshot, dict) else {}
        rows.append(
            {
                "invoice_id": str(inv.id),
                "access_key": inv.access_key,
                "status": inv.status,
                "issue_date": inv.issue_date.isoformat(),
                "number": inv.number,
                "series": inv.series,
                "total_cents": inv.total_cents,
                "payment_amount_cents": inv.payment_amount_cents,
                "provider_cnpj": inv.provider.document if inv.provider_id else "",
                "customer_document": inv.customer.document if inv.customer_id else "",
                "catalog_version": snap.get("catalog_version"),
                "rtc_mode": (snap.get("totals") or {}).get("rtc_mode"),
                "rtc_totals": (snap.get("totals") or {}).get("rtc"),
                "forensic_sha256": (snap.get("forensic") or {}).get("forensic_sha256"),
                "payload_hash": inv.payload_hash,
            }
        )

    manifest = {
        "schema": "exeq.nfe.competence_export.v1",
        "tenant_id": str(tenant_id),
        "competence": f"{year:04d}-{month:02d}",
        "count": len(rows),
        "invoices": rows,
    }
    path = out_dir / f"nfe-competence-{year:04d}-{month:02d}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "count": len(rows), "competence": manifest["competence"]}
