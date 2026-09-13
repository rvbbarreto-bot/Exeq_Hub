"""Planos e assinaturas do tenant."""

from __future__ import annotations

from django.utils import timezone

from apps.accounts.models import Plan, Subscription

# Catálogo seed (mercado contábil). limits null em chave = sem teto.
SYSTEM_PLANS: tuple[dict, ...] = (
    {
        "code": "starter",
        "name": "Starter",
        "sort_order": 10,
        "limits": {"max_emit_cnpjs": 1, "max_users": 2, "max_nf_month": 50},
    },
    {
        "code": "contabil_5",
        "name": "Contábil 5",
        "sort_order": 20,
        "limits": {"max_emit_cnpjs": 5, "max_users": 5, "max_nf_month": 500},
    },
    {
        "code": "contabil_20",
        "name": "Contábil 20",
        "sort_order": 30,
        "limits": {"max_emit_cnpjs": 20, "max_users": 15, "max_nf_month": 2000},
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "sort_order": 40,
        "limits": {},  # ilimitado até feature flags
    },
)

def ensure_system_plans() -> list[Plan]:
    out: list[Plan] = []
    for item in SYSTEM_PLANS:
        plan, _ = Plan.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "is_active": True,
                "limits": item.get("limits") or {},
                "sort_order": item.get("sort_order") or 0,
            },
        )
        out.append(plan)
    return out


def assign_plan(
    *,
    tenant,
    plan: Plan | str,
    status: str = Subscription.Status.ACTIVE,
) -> Subscription:
    """Cria ou atualiza a assinatura do tenant (1:1)."""
    if isinstance(plan, str):
        plan_obj = Plan.objects.filter(code=plan, is_active=True).first()
        if plan_obj is None:
            ensure_system_plans()
            plan_obj = Plan.objects.filter(code=plan).first()
        if plan_obj is None:
            raise ValueError(f"Plano desconhecido: {plan}")
        plan = plan_obj

    now = timezone.now()
    sub, created = Subscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            "plan": plan,
            "status": status,
            "current_period_start": now,
        },
    )
    if not created:
        sub.plan = plan
        sub.status = status
        if sub.current_period_start is None:
            sub.current_period_start = now
        sub.save()
    return sub
