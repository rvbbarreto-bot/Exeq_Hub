"""Spike HTTP homolog SP — preflight ALE (certificado + IE)."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.accounts.certificates import get_primary_certificate
from apps.accounts.models import DigitalCertificate, Tenant
from apps.fiscal.rtc_emit_readiness import assess_rtc_emit_readiness
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.exceptions import NfeDisabledError, NfeValidationError
from apps.nfe.gate import build_gate_payload
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items

ALE_TENANT_SLUG = "ALE"
ALE_CNPJ = "61536366000174"


def build_homolog_preflight(
    *,
    tenant,
    provider: Provider,
    http_mode: str = "http",
    rtc_mode: str | None = None,
    issue_date: date | str | None = None,
) -> dict[str, Any]:
    """Checklist pré-spike: gate T0 + cert A1 + IE + RTC emit."""
    mode = (http_mode or "http").lower()
    gate = build_gate_payload(tenant=tenant, provider_id=str(provider.id))
    must_fail = [c for c in gate.get("checks") or [] if c.get("must") and not c.get("ok")]

    cert = get_primary_certificate(tenant=tenant, cnpj=provider.document)
    cert_detail: dict[str, Any] = {"present": cert is not None}
    if cert is not None:
        cert_detail.update(
            {
                "status": cert.status,
                "not_after": cert.not_after.isoformat() if cert.not_after else None,
            }
        )

    ie = (provider.state_registration or "").strip()
    rtc = assess_rtc_emit_readiness(
        document_model="55",
        issue_date=issue_date or date.today(),
    )
    if rtc_mode == "emit" and not rtc["ok"]:
        must_fail.extend([{"id": b, "ok": False, "must": True} for b in rtc["blockers"]])

    blockers = [c.get("id") or c.get("label") for c in must_fail]
    if mode == "http" and not ie and not (ie.upper() in {"ISENTO", "ISENTA"}):
        blockers.append("ie_missing")
    if mode == "http" and cert is None:
        blockers.append("cert_missing")
    elif mode == "http" and cert and cert.status not in {
        DigitalCertificate.Status.ACTIVE,
        DigitalCertificate.Status.EXPIRING,
    }:
        blockers.append(f"cert_status_{cert.status}")

    uf = (provider.address or {}).get("uf") if isinstance(provider.address, dict) else ""
    return {
        "ok": len(blockers) == 0,
        "tenant": getattr(tenant, "slug", ""),
        "cnpj": provider.document,
        "uf": uf,
        "http_mode": mode,
        "ie_present": bool(ie),
        "cert": cert_detail,
        "gate_can_create": gate.get("can_create"),
        "gate_checks": gate.get("checks"),
        "rtc_emit": rtc,
        "blockers": blockers,
        "pilot_note": "ALE v1: CFOP 5102 only (sem ST); use --ncm 21069090",
    }


def run_homolog_spike(
    *,
    tenant: Tenant,
    provider: Provider,
    customer: Customer,
    mode: str = "stub",
    dry_run: bool = False,
    series: int = 1,
    valor_cents: int = 1500,
    ncm: str = "21069090",
    rtc_mode: str | None = None,
    issue_date: date | None = None,
) -> tuple[NfeInvoice, dict[str, Any]]:
    """Emite 1 NF-e spike; retorna invoice + preflight/evidence base."""
    preflight = build_homolog_preflight(
        tenant=tenant,
        provider=provider,
        http_mode=mode,
        rtc_mode=rtc_mode,
        issue_date=issue_date,
    )
    if mode == "http" and not dry_run and not preflight["ok"]:
        raise NfeValidationError(
            f"preflight homolog falhou: {', '.join(preflight['blockers'])}"
        )

    overrides: dict[str, Any] = {
        "NFE_ENABLED": True,
        "NFE_HTTP_MODE": mode,
        "NFE_HTTP_DRY_RUN": dry_run if mode == "http" else False,
        "NFE_DEFAULT_TP_AMB": "2",
    }
    if rtc_mode:
        overrides["NFE_RTC_MODE"] = rtc_mode

    from django.test.utils import override_settings

    product_code = f"SPIKE-{uuid.uuid4().hex[:6].upper()}"
    idem = f"nfe-spike-{uuid.uuid4().hex[:12]}"
    with override_settings(**overrides):
        product = create_product(
            tenant=tenant,
            code=product_code,
            description="Item spike homolog SP",
            ncm=ncm,
            unit_price_cents=int(valor_cents),
            csosn="102",
        )
        inv = create_draft(
            tenant=tenant,
            provider=provider,
            customer=customer,
            idempotency_key=idem,
            series=int(series),
            nature_operation="VENDA SPIKE HOMOLOG",
            actor="nfe_spike_homolog",
        )
        if issue_date:
            inv.issue_date = issue_date
            inv.save(update_fields=["issue_date", "updated_at"])
        elif inv.issue_date is None:
            inv.issue_date = date.today()
            inv.save(update_fields=["issue_date", "updated_at"])
        replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
        inv.refresh_from_db()
        inv = emit_invoice(inv, actor="nfe_spike_homolog")

    inv.refresh_from_db()
    return inv, preflight


def write_spike_evidence(
    *,
    inv: NfeInvoice,
    provider: Provider,
    preflight: dict[str, Any],
    mode: str,
    dry_run: bool,
    out: Path,
    tenant_slug: str,
) -> dict[str, Any]:
    """Monta JSON auditável (sem secrets)."""
    from apps.nfe.artifacts import has_danfe_pdf, has_xml_authorized

    events = list(
        inv.events.order_by("-occurred_at")[:5].values(
            "from_status", "to_status", "actor", "metadata", "occurred_at"
        )
    )
    last_raw: dict[str, Any] = {}
    if events:
        m0 = events[0].get("metadata") or {}
        if isinstance(m0, dict) and isinstance(m0.get("raw"), dict):
            last_raw = {
                k: v
                for k, v in m0["raw"].items()
                if k in {"cStat", "xMotivo", "nProt", "chNFe", "nRec", "http"}
            }
    c_stat = str(last_raw.get("cStat") or inv.rejection_code or "")
    g_spike = (
        mode == "http"
        and not dry_run
        and inv.status == NfeInvoice.Status.AUTHORIZED
        and c_stat in {"100", "150", ""}
    )
    art_xml = has_xml_authorized(inv) if inv.status == NfeInvoice.Status.AUTHORIZED else False
    art_pdf = has_danfe_pdf(inv) if inv.status == NfeInvoice.Status.AUTHORIZED else False
    evidence = {
        "schema_version": "1.1",
        "gate": "G-NFE-SPIKE-ALE",
        "preflight": preflight,
        "g_spike_candidate": g_spike,
        "artifacts": {"xml_authorized": art_xml, "danfe_pdf": art_pdf},
        "tenant": tenant_slug,
        "cnpj": provider.document,
        "mode": mode,
        "dry_run": dry_run,
        "invoice_id": str(inv.id),
        "status": inv.status,
        "access_key": inv.access_key or "",
        "protocol": inv.protocol or "",
        "cStat": c_stat,
        "sefaz_raw_safe": last_raw,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence
