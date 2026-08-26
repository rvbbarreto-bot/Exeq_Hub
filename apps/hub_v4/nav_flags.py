"""Flags de navegação e feature por tenant (Hub V4)."""

from __future__ import annotations

from django.conf import settings

from apps.accounts.models import Tenant
from apps.accounts.permissions import FOOD_ONLY_ROLES
from apps.accounts.plan_limits import provider_usage
from apps.hub_v4.active_company import get_active_provider
from apps.hub_v4.auth import SESSION_ROLE, SESSION_TENANT, SESSION_TENANT_SLUG


def nfe_product_enabled() -> bool:
    return bool(getattr(settings, "NFE_ENABLED", False))


def nfe_enabled_for_tenant(tenant) -> bool:
    """
    NF-e visível no Hub para o tenant:
    - flag global NFE_ENABLED=true
    - e tenant.settings.nfe_enabled == true (opt-in por cliente)
    """
    if not nfe_product_enabled() or tenant is None:
        return False
    cfg = tenant.settings if isinstance(tenant.settings, dict) else {}
    return bool(cfg.get("nfe_enabled"))


def hub_nav_flags(request):
    out = {
        "nfe_enabled_nav": False,
        "nfe_product_enabled": nfe_product_enabled(),
        "active_provider": None,
        "provider_usage": None,
        "is_platform_user": False,
        "food_only_nav": False,
        "hub_tenant_slug": request.session.get(SESSION_TENANT_SLUG) or "",
        "hub_tenant_name": request.session.get("hub_v4_tenant_name") or "",
        "hub_user_name": request.session.get("hub_v4_user_name") or "",
    }
    tid = request.session.get(SESSION_TENANT)
    role = request.session.get(SESSION_ROLE) or ""
    out["food_only_nav"] = role in FOOD_ONLY_ROLES
    if not tid:
        return out
    tenant = Tenant.objects.filter(pk=tid).only("id", "settings", "slug", "legal_name").first()
    if tenant is not None and not out["hub_tenant_slug"]:
        out["hub_tenant_slug"] = tenant.slug
    if tenant is None:
        return out
    out["nfe_enabled_nav"] = nfe_enabled_for_tenant(tenant)
    out["active_provider"] = get_active_provider(request, tenant)
    out["provider_usage"] = provider_usage(tenant)
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        out["is_platform_user"] = bool(
            getattr(user, "is_platform_admin", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )
    return out
