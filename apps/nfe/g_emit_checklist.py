"""Checklist G-EMIT pré-envio (sem POST SEFAZ) — ops readiness."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.master_data.models import Provider
from apps.nfe.gate import build_gate_payload, http_mode
from apps.nfe.services import nfe_feature_enabled
from apps.nfe.catalog import CATALOG_VERSION


def build_g_emit_checklist(
    *,
    tenant,
    provider_id: str | None = None,
    series: int | None = None,
    tp_amb: str | None = None,
    cnpj: str | None = None,
) -> dict[str, Any]:
    """
    Consolida gate T0 + env + pré-reqs ops para o runbook G-EMIT.

    Não acessa SEFAZ. `ready_for_http_emit` = can_create + modo http + flag on.
    """
    provider = None
    if provider_id:
        provider = Provider.objects.filter(
            tenant=tenant, id=provider_id, is_active=True
        ).first()
    if provider is None and cnpj:
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        provider = (
            Provider.objects.filter(tenant=tenant, document=digits, is_active=True).first()
            or Provider.objects.filter(tenant=tenant, document=digits).first()
        )

    gate = build_gate_payload(
        tenant=tenant,
        provider_id=str(provider.id) if provider else provider_id,
        series=series,
        tp_amb=tp_amb,
    )
    mode = http_mode()
    dry_run = bool(getattr(settings, "NFE_HTTP_DRY_RUN", False))
    enabled = nfe_feature_enabled()
    must_fail = [c for c in gate.get("checks") or [] if c.get("must") and not c.get("ok")]
    warn = [c for c in gate.get("checks") or [] if not c.get("must") and not c.get("ok")]

    ready = bool(
        enabled
        and gate.get("can_create")
        and mode == "http"
        and not dry_run
        and not must_fail
    )
    dry_ready = bool(
        enabled and gate.get("can_create") and mode == "http" and not must_fail
    )

    blockers = [c["id"] for c in must_fail]
    if not enabled:
        blockers.append("nfe_enabled")
    if mode != "http":
        blockers.append("http_mode")
    if dry_run and mode == "http":
        blockers.append("http_dry_run")

    runbook_cmds = []
    slug = getattr(tenant, "slug", "")
    doc = ""
    if provider is not None:
        doc = "".join(ch for ch in str(provider.document or "") if ch.isdigit())
    if slug and doc:
        runbook_cmds = [
            f"python manage.py nfe_spike_sefaz --tenant {slug} --cnpj {doc} --mode http --dry-run",
            f"python manage.py nfe_spike_sefaz --tenant {slug} --cnpj {doc} --mode http "
            f"--out .storage/nfe_g_emit_sp_evidence.json",
        ]

    return {
        "schema_version": "1.0",
        "purpose": "g_emit_checklist",
        "ready_for_http_emit": ready,
        "ready_for_http_dry_run": dry_ready,
        "blockers": blockers,
        "warnings": [c["id"] for c in warn],
        "env": {
            "NFE_ENABLED": enabled,
            "NFE_HTTP_MODE": mode,
            "NFE_HTTP_DRY_RUN": dry_run,
            "NFE_PIVOT_UF": getattr(settings, "NFE_PIVOT_UF", "SP"),
            "NFE_DEFAULT_TP_AMB": str(getattr(settings, "NFE_DEFAULT_TP_AMB", "2")),
            "catalog_version": CATALOG_VERSION,
        },
        "gate": {
            "can_create": gate.get("can_create"),
            "checks": gate.get("checks"),
            "provider_id": gate.get("provider_id"),
            "series": gate.get("series"),
            "tp_amb": gate.get("tp_amb"),
            "next_number_estimated": gate.get("next_number_estimated"),
            "supported_ufs": gate.get("supported_ufs"),
        },
        "runbook": "Docs/Exeq_Hub_NFe_U5_Interestadual_CCe_G_EMIT.md",
        "runbook_commands": runbook_cmds,
        "note": (
            "ready_for_http_emit=true NÃO autoriza G-EMIT — só pré-req local. "
            "G-EMIT exige authorized + XML + DANFE + chave 35… e g_emit_candidate no spike."
            if ready
            else "Corrija blockers antes do spike HTTP real."
        ),
    }
