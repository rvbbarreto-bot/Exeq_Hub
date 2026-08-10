"""Sessão web do Hub V4 (tenant-scoped). Não altera JWT/API."""

from __future__ import annotations

from django.http import HttpRequest
from django.shortcuts import redirect

from apps.accounts.models import Tenant, TenantMembership, User

SESSION_TENANT = "hub_v4_tenant_id"
SESSION_USER = "hub_v4_user_id"
SESSION_ROLE = "hub_v4_role_code"
SESSION_TENANT_NAME = "hub_v4_tenant_name"
SESSION_USER_NAME = "hub_v4_user_name"
# Compat: reutiliza sessão de /cadastros/ se já autenticada
CADASTRO_TENANT = "cadastro_tenant_id"
CADASTRO_USER = "cadastro_user_id"
CADASTRO_ROLE = "cadastro_role_code"
CADASTRO_TENANT_NAME = "cadastro_tenant_name"
CADASTRO_USER_NAME = "cadastro_user_name"


def adopt_cadastro_session(request: HttpRequest) -> bool:
    tid = request.session.get(CADASTRO_TENANT)
    uid = request.session.get(CADASTRO_USER)
    role = request.session.get(CADASTRO_ROLE)
    if not (tid and uid and role):
        return False
    request.session[SESSION_TENANT] = tid
    request.session[SESSION_USER] = uid
    request.session[SESSION_ROLE] = role
    request.session[SESSION_TENANT_NAME] = request.session.get(
        CADASTRO_TENANT_NAME, ""
    )
    request.session[SESSION_USER_NAME] = request.session.get(CADASTRO_USER_NAME, "")
    return True


def session_ok(request: HttpRequest) -> bool:
    if request.session.get(SESSION_TENANT) and request.session.get(SESSION_USER):
        return True
    return adopt_cadastro_session(request)


def require_hub(request: HttpRequest):
    if not session_ok(request):
        return None, None, None, redirect("hub-v4-login")
    tenant = Tenant.objects.filter(pk=request.session[SESSION_TENANT]).first()
    user = User.objects.filter(pk=request.session[SESSION_USER]).first()
    if tenant is None or user is None:
        for k in list(request.session.keys()):
            if k.startswith("hub_v4_"):
                del request.session[k]
        return None, None, None, redirect("hub-v4-login")
    role = request.session.get(SESSION_ROLE) or ""
    mem = (
        TenantMembership.objects.filter(tenant=tenant, user=user, is_active=True)
        .select_related("role")
        .first()
    )
    if mem is None:
        return None, None, None, redirect("hub-v4-login")
    if not role:
        role = mem.role.code
        request.session[SESSION_ROLE] = role
    return tenant, user, role, None


def set_hub_session(
    request: HttpRequest,
    *,
    user: User,
    tenant: Tenant,
    role_code: str,
) -> None:
    request.session[SESSION_TENANT] = str(tenant.id)
    request.session[SESSION_USER] = str(user.id)
    request.session[SESSION_ROLE] = role_code
    request.session[SESSION_TENANT_NAME] = tenant.legal_name or tenant.slug
    request.session[SESSION_USER_NAME] = user.name or user.email
    # Espelha cadastros para SSO
    request.session[CADASTRO_TENANT] = str(tenant.id)
    request.session[CADASTRO_USER] = str(user.id)
    request.session[CADASTRO_ROLE] = role_code
    request.session[CADASTRO_TENANT_NAME] = tenant.legal_name or tenant.slug
    request.session[CADASTRO_USER_NAME] = user.name or user.email


def clear_hub_session(request: HttpRequest) -> None:
    from apps.hub_v4.active_company import SESSION_ACTIVE_PROVIDER

    for key in (
        SESSION_TENANT,
        SESSION_USER,
        SESSION_ROLE,
        SESSION_TENANT_NAME,
        SESSION_USER_NAME,
        SESSION_ACTIVE_PROVIDER,
        CADASTRO_TENANT,
        CADASTRO_USER,
        CADASTRO_ROLE,
        CADASTRO_TENANT_NAME,
        CADASTRO_USER_NAME,
        "cadastro_access_token",
    ):
        request.session.pop(key, None)
