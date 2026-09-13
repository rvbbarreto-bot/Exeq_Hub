"""Texto livre por emissão (xDescServ / xInfComp) — alinhado layout NFS-e Nacional."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.issuance.models import NfIssue

MAX_DESCRICAO_SERVICO = 1000
MAX_INFORMACOES_COMPLEMENTARES = 2000


def _collapse_ws(text: str) -> str:
    """SEFIN rejeita quebras de linha em xDescServ/xInfComp (TSDescInfCompl)."""
    return " ".join(str(text or "").split())


def normalize_emission_fields(
    *,
    descricao_servico: str = "",
    informacoes_complementares: str = "",
    codigo_nbs: str = "",
) -> dict[str, str]:
    from apps.master_data.nbs_import import normalize_nbs_code

    out: dict[str, str] = {}
    desc = _collapse_ws(descricao_servico)[:MAX_DESCRICAO_SERVICO]
    comp = _collapse_ws(informacoes_complementares)[:MAX_INFORMACOES_COMPLEMENTARES]
    nbs = normalize_nbs_code(codigo_nbs)
    if desc:
        out["descricao_servico"] = desc
    if comp:
        out["informacoes_complementares"] = comp
    if len(nbs) == 9:
        out["codigo_nbs"] = nbs
    return out


def draft_emission(issue: NfIssue) -> dict[str, str]:
    raw = issue.internal_payload or {}
    block = raw.get("emission") if isinstance(raw, dict) else None
    return dict(block) if isinstance(block, dict) else {}


def resolve_emission_text(issue: NfIssue) -> tuple[str, str]:
    params = issue.resolved_params or {}
    draft = draft_emission(issue)
    desc = (
        params.get("descricao_servico")
        or draft.get("descricao_servico")
        or getattr(issue.service, "description", None)
        or "Servico"
    )
    comp = params.get("informacoes_complementares") or draft.get("informacoes_complementares") or ""
    return (
        _collapse_ws(desc)[:MAX_DESCRICAO_SERVICO],
        _collapse_ws(comp)[:MAX_INFORMACOES_COMPLEMENTARES],
    )
