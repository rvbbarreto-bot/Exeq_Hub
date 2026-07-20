"""Deprecated — use integrations.nfse.factory.get_nfse_provider (Focus default)."""

from integrations.nfse.factory import get_nfse_provider


def emit_nfse(*, issue) -> dict:
    provider = get_nfse_provider(
        ibge_code=issue.ibge_code,
        tenant_settings=getattr(issue.tenant, "settings", None) or {},
    )
    result = provider.emitir(payload={"issue_id": str(issue.id)})
    return {
        "focus_ref": result.external_ref,
        "status": result.status,
        "raw": result.raw,
    }
