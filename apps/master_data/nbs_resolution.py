"""Resolução do código NBS na emissão NFS-e (override > draft > serviço)."""

from __future__ import annotations

from apps.master_data.nbs_import import normalize_nbs_code


def resolve_codigo_nbs(
    *,
    service,
    params: dict | None = None,
    draft_emission: dict | None = None,
) -> str:
    params = params or {}
    draft_emission = draft_emission or {}
    for raw in (
        draft_emission.get("codigo_nbs"),
        params.get("codigo_nbs"),
        getattr(service, "codigo_nbs", None),
    ):
        if raw is None:
            continue
        code = normalize_nbs_code(str(raw))
        if len(code) == 9:
            return code
    nbs_item = getattr(service, "nbs_item", None)
    if nbs_item is not None and getattr(nbs_item, "codigo", ""):
        code = normalize_nbs_code(str(nbs_item.codigo))
        if len(code) == 9:
            return code
    return ""
