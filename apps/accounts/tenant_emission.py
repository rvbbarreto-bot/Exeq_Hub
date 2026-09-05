"""Tipos de emissão fiscal habilitados por tenant (NFS-e / NF-e / NFC-e)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

NFSE_ENABLED_KEY = "nfse_enabled"
NFE_ENABLED_KEY = "nfe_enabled"
NFCE_ENABLED_KEY = "nfce_enabled"


def tenant_settings_dict(tenant) -> dict[str, Any]:
    if tenant is None:
        return {}
    raw = getattr(tenant, "settings", None)
    return dict(raw) if isinstance(raw, dict) else {}


def nfse_enabled_for_tenant(tenant) -> bool:
    """
    NFS-e habilitada no tenant.
    Default True quando a chave não existe (compatibilidade com tenants legados).
    """
    if tenant is None:
        return False
    cfg = tenant_settings_dict(tenant)
    if NFSE_ENABLED_KEY not in cfg:
        return True
    return bool(cfg.get(NFSE_ENABLED_KEY))


def nfe_tenant_opt_in(tenant) -> bool:
    """Opt-in NF-e no tenant (sem checar flag global)."""
    if tenant is None:
        return False
    return bool(tenant_settings_dict(tenant).get(NFE_ENABLED_KEY))


def nfce_tenant_opt_in(tenant) -> bool:
    """Opt-in NFC-e no tenant (sem checar flag global)."""
    if tenant is None:
        return False
    return bool(tenant_settings_dict(tenant).get(NFCE_ENABLED_KEY))


def nfe_global_enabled() -> bool:
    return bool(getattr(settings, "NFE_ENABLED", False))


def nfce_global_enabled() -> bool:
    return bool(getattr(settings, "NFCE_ENABLED", False))


def nfe_enabled_for_tenant(tenant) -> bool:
    """NF-e visível/operação: flag global + opt-in tenant."""
    if not nfe_global_enabled() or tenant is None:
        return False
    return nfe_tenant_opt_in(tenant)


def nfce_enabled_for_tenant(tenant) -> bool:
    """NFC-e visível/operação: flag global + opt-in tenant."""
    if not nfce_global_enabled() or tenant is None:
        return False
    return nfce_tenant_opt_in(tenant)


def apply_emission_flags(
    settings_map: dict[str, Any] | None,
    *,
    nfse: bool,
    nfe: bool,
    nfce: bool | None = None,
) -> dict[str, Any]:
    """Mescla flags de emissão preservando demais chaves de settings."""
    out = dict(settings_map) if isinstance(settings_map, dict) else {}
    out[NFSE_ENABLED_KEY] = bool(nfse)
    out[NFE_ENABLED_KEY] = bool(nfe)
    if nfce is not None:
        out[NFCE_ENABLED_KEY] = bool(nfce)
    return out


def default_emission_settings(*, nfse: bool = True, nfe: bool = False, nfce: bool = False) -> dict[str, Any]:
    return apply_emission_flags({}, nfse=nfse, nfe=nfe, nfce=nfce)


def emission_flags_from_settings(settings_map: dict[str, Any] | None) -> tuple[bool, bool, bool]:
    cfg = settings_map if isinstance(settings_map, dict) else {}
    nfse = bool(cfg.get(NFSE_ENABLED_KEY)) if NFSE_ENABLED_KEY in cfg else True
    nfe = bool(cfg.get(NFE_ENABLED_KEY))
    nfce = bool(cfg.get(NFCE_ENABLED_KEY))
    return nfse, nfe, nfce
