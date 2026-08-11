"""
Entitlements comerciais: Subscription.plan.limits com fallback em tenant.settings.

Chaves conhecidas no Plan.limits:
- max_emit_cnpjs — Prestadores ativos (CNPJ emitente)
- max_users — memberships ativas
- max_nf_month — NFS-e criadas no mês civil (exceto canceladas)
"""

from __future__ import annotations

from typing import Any

from shared.exceptions import DomainError

SETTINGS_MAX_EMIT_CNPJS = "max_emit_cnpjs"
LIMIT_MAX_EMIT_CNPJS = "max_emit_cnpjs"
LIMIT_MAX_USERS = "max_users"
LIMIT_MAX_NF_MONTH = "max_nf_month"


class PlanLimitError(DomainError):
    code = "plan_limit_exceeded"


def _settings_dict(tenant) -> dict[str, Any]:
    cfg = getattr(tenant, "settings", None)
    return cfg if isinstance(cfg, dict) else {}


def _coerce_int_limit(raw) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return n


def get_subscription(tenant):
    if tenant is None:
        return None
    from apps.accounts.models import Subscription

    try:
        return Subscription.objects.select_related("plan").get(tenant_id=tenant.pk)
    except Subscription.DoesNotExist:
        return None


def plan_limits_dict(tenant) -> dict[str, Any]:
    sub = get_subscription(tenant)
    if sub is None or not sub.is_entitled:
        return {}
    limits = getattr(sub.plan, "limits", None)
    return limits if isinstance(limits, dict) else {}


def resolve_limit(tenant, key: str) -> int | None:
    """
    Ordem:
    1) tenant.settings[key] se definido (override operacional)
    2) plan.limits[key] se assinatura trialing/active
    3) None = sem teto
    """
    cfg = _settings_dict(tenant)
    if key in cfg and cfg.get(key) is not None and cfg.get(key) != "":
        return _coerce_int_limit(cfg.get(key))
    return _coerce_int_limit(plan_limits_dict(tenant).get(key))


def max_emit_cnpjs(tenant) -> int | None:
    return resolve_limit(tenant, LIMIT_MAX_EMIT_CNPJS)


def max_users(tenant) -> int | None:
    return resolve_limit(tenant, LIMIT_MAX_USERS)


def max_nf_month(tenant) -> int | None:
    return resolve_limit(tenant, LIMIT_MAX_NF_MONTH)


def active_provider_count(tenant) -> int:
    from apps.master_data.models import Provider

    return Provider.objects.filter(tenant=tenant, is_active=True).count()


def active_user_count(tenant) -> int:
    from apps.accounts.models import TenantMembership

    return TenantMembership.objects.filter(tenant=tenant, is_active=True).count()


def nf_issues_this_month(tenant) -> int:
    from django.utils import timezone

    from apps.issuance.models import NfIssue

    now = timezone.localtime()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        NfIssue.objects.filter(tenant=tenant, created_at__gte=start)
        .exclude(status=NfIssue.Status.CANCELLED)
        .count()
    )


def _usage_block(used: int, limit: int | None) -> dict[str, Any]:
    return {
        "used": used,
        "limit": limit,
        "unlimited": limit is None,
        "remaining": None if limit is None else max(0, limit - used),
        "at_limit": False if limit is None else used >= limit,
        "label": f"{used}/∞" if limit is None else f"{used}/{limit}",
    }


def provider_usage(tenant) -> dict[str, Any]:
    used = active_provider_count(tenant)
    limit = max_emit_cnpjs(tenant)
    sub = get_subscription(tenant)
    cfg = _settings_dict(tenant)
    source = "unlimited"
    if limit is not None:
        if cfg.get(SETTINGS_MAX_EMIT_CNPJS) not in (None, ""):
            source = "settings_override"
        elif sub and sub.is_entitled:
            source = "subscription"
        else:
            source = "settings"
    block = _usage_block(used, limit)
    plan_name = ""
    plan_code = ""
    sub_status = ""
    if sub and sub.plan_id:
        plan_name = sub.plan.name
        plan_code = sub.plan.code
        sub_status = sub.status
    block.update(
        {
            "plan_name": plan_name,
            "plan_code": plan_code,
            "subscription_status": sub_status,
            "source": source,
            "users": _usage_block(active_user_count(tenant), max_users(tenant)),
            "nf_month": _usage_block(nf_issues_this_month(tenant), max_nf_month(tenant)),
        }
    )
    return block


def can_add_active_provider(tenant, *, extra_active: int = 1) -> bool:
    limit = max_emit_cnpjs(tenant)
    if limit is None:
        return True
    return active_provider_count(tenant) + extra_active <= limit


def assert_can_add_active_provider(tenant, *, extra_active: int = 1) -> None:
    if can_add_active_provider(tenant, extra_active=extra_active):
        return
    usage = provider_usage(tenant)
    plan_hint = f" ({usage['plan_name']})" if usage.get("plan_name") else ""
    raise PlanLimitError(
        f"Limite do plano atingido{plan_hint}: {usage['used']}/{usage['limit']} "
        f"CNPJ(s) emitente(s) ativos. Desative uma empresa ou solicite upgrade do plano."
    )


def can_add_active_user(tenant, *, extra_active: int = 1) -> bool:
    limit = max_users(tenant)
    if limit is None:
        return True
    return active_user_count(tenant) + extra_active <= limit


def assert_can_add_active_user(tenant, *, extra_active: int = 1) -> None:
    if can_add_active_user(tenant, extra_active=extra_active):
        return
    usage = provider_usage(tenant)
    u = usage["users"]
    plan_hint = f" ({usage['plan_name']})" if usage.get("plan_name") else ""
    raise PlanLimitError(
        f"Limite de usuários do plano atingido{plan_hint}: {u['used']}/{u['limit']}. "
        "Desative um vínculo ou solicite upgrade."
    )


def can_create_nf_this_month(tenant, *, extra: int = 1) -> bool:
    limit = max_nf_month(tenant)
    if limit is None:
        return True
    return nf_issues_this_month(tenant) + extra <= limit


def assert_can_create_nf_this_month(tenant, *, extra: int = 1) -> None:
    if can_create_nf_this_month(tenant, extra=extra):
        return
    usage = provider_usage(tenant)
    n = usage["nf_month"]
    plan_hint = f" ({usage['plan_name']})" if usage.get("plan_name") else ""
    raise PlanLimitError(
        f"Limite mensal de NFS-e do plano atingido{plan_hint}: {n['used']}/{n['limit']}. "
        "Aguarde o próximo mês ou solicite upgrade."
    )
