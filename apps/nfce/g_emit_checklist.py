"""Checklist G-EMIT-NFCE — prontidão homolog SP (sem POST SEFAZ)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.master_data.models import Provider
from apps.nfce.gate import build_gate_payload, http_mode
from apps.nfce.services import nfce_feature_enabled


def build_g_emit_checklist(
    *,
    tenant,
    provider_id: str | None = None,
    series: int | None = None,
    tp_amb: str | None = None,
    cnpj: str | None = None,
) -> dict[str, Any]:
    provider = None
    if provider_id:
        provider = Provider.objects.filter(
            tenant=tenant, id=provider_id, is_active=True
        ).first()
    if provider is None and cnpj:
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        provider = Provider.objects.filter(
            tenant=tenant, document=digits, is_active=True
        ).first()

    gate = build_gate_payload(
        tenant=tenant,
        provider_id=str(provider.id) if provider else provider_id,
        series=series,
        tp_amb=tp_amb,
    )
    mode = http_mode()
    dry_run = bool(getattr(settings, "NFCE_HTTP_DRY_RUN", False))
    enabled = nfce_feature_enabled()
    must_fail = [c for c in gate.get("checks") or [] if c.get("must") and not c.get("ok")]
    warn = [c for c in gate.get("checks") or [] if not c.get("must") and not c.get("ok")]

    ready = bool(
        enabled and gate.get("can_create") and mode == "http" and not dry_run and not must_fail
    )
    dry_ready = bool(enabled and gate.get("can_create") and mode == "http" and not must_fail)

    blockers = [c["id"] for c in must_fail]
    if not enabled:
        blockers.append("nfce_enabled")
    if mode != "http":
        blockers.append("http_mode")
    if dry_run and mode == "http":
        blockers.append("http_dry_run")

    return {
        "schema_version": "1.0",
        "purpose": "g_emit_nfce_checklist",
        "ready_for_http_emit": ready,
        "ready_for_http_dry_run": dry_ready,
        "blockers": blockers,
        "warnings": [c["id"] for c in warn],
        "env": {
            "NFCE_ENABLED": enabled,
            "NFCE_HTTP_MODE": mode,
            "NFCE_HTTP_DRY_RUN": dry_run,
            "NFCE_DEFAULT_TP_AMB": str(getattr(settings, "NFCE_DEFAULT_TP_AMB", "2")),
            "NFCE_RTC_MODE": getattr(settings, "NFCE_RTC_MODE", "shadow"),
            "NFE_PIVOT_UF": getattr(settings, "NFE_PIVOT_UF", "SP"),
        },
        "gate": {
            "can_create": gate.get("can_create"),
            "checks": gate.get("checks"),
            "provider_id": gate.get("provider_id"),
            "series": gate.get("series"),
            "tp_amb": gate.get("tp_amb"),
            "next_number_estimated": gate.get("next_number_estimated"),
        },
        "runbook": "Docs/Exeq_Hub_LLR_NFCE_Emissao_PDV_Kickoff.md",
        "note": (
            "ready_for_http_emit=true é pré-req local. "
            "G-EMIT-NFCE exige authorized + XML mod65 + DANFE cupom + CSC válido em homolog."
            if ready
            else "Corrija blockers antes do spike HTTP homolog SP."
        ),
    }
