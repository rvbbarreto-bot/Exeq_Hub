"""Feature flags NF-e de entrada."""

from __future__ import annotations

from django.conf import settings

from apps.accounts.models import Tenant
from apps.nfe.entrada.exceptions import NfeEntradaDisabledError


def nfe_entrada_global_enabled() -> bool:
    return bool(getattr(settings, "NFE_ENTRADA_ENABLED", False))


def nfe_entrada_enabled_for_tenant(tenant: Tenant) -> bool:
    if not nfe_entrada_global_enabled():
        return False
    cfg = tenant.settings or {}
    return bool(cfg.get("nfe_entrada_enabled", False))


def require_nfe_entrada_enabled(*, tenant: Tenant) -> None:
    if not nfe_entrada_enabled_for_tenant(tenant):
        raise NfeEntradaDisabledError("Captura NF-e de entrada desabilitada para este tenant.")
