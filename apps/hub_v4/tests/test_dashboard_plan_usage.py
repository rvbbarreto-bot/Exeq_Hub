"""Painel: uso do plano (CNPJs, usuários, NFS-e mês) + pendências de limite."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.plan_services import assign_plan, ensure_system_plans
from apps.accounts.services import ensure_system_roles
from apps.hub_v4.services import dashboard_context
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider


@pytest.fixture
def hub_dash(db):
    roles = {r.code: r for r in ensure_system_roles()}
    ensure_system_plans()
    tenant = Tenant.objects.create(
        slug="dash-plan-qa",
        legal_name="Dash Plan QA",
        document="60746948000112",
    )
    user = User.objects.create_user(
        email="dash.plan@exeq.local", password="Secret123!", name="Dash Plan"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    assign_plan(tenant=tenant, plan="starter")  # 1 CNPJ, 2 users, 50 NF
    return tenant, user


@pytest.mark.django_db
def test_dashboard_context_includes_plan_usage(hub_dash):
    tenant, _ = hub_dash
    ctx = dashboard_context(tenant)
    assert ctx["usage"]["plan_code"] == "starter"
    assert len(ctx["usage_rows"]) == 3
    keys = {r["key"] for r in ctx["usage_rows"]}
    assert keys == {"providers", "users", "nf_month"}
    assert ctx["usage"]["users"]["used"] == 1
    assert ctx["usage"]["users"]["limit"] == 2


@pytest.mark.django_db
def test_dashboard_pending_when_cnpj_limit(hub_dash):
    tenant, _ = hub_dash
    create_provider(
        tenant=tenant,
        legal_name="Emit One",
        document="11222333000181",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
    )
    ctx = dashboard_context(tenant)
    assert ctx["usage"]["at_limit"] is True
    titles = " ".join(a["title"] for a in ctx["pending_actions"])
    assert "Limite de CNPJs" in titles


@pytest.mark.django_db
def test_dashboard_renders_plan_section(client, hub_dash):
    tenant, user = hub_dash
    client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )
    r = client.get(reverse("hub-v4-dashboard"))
    assert r.status_code == 200
    html = r.content.decode()
    assert "Uso do plano" in html
    assert "Starter" in html
    assert "CNPJs emitentes" in html
    assert "Usuários ativos" in html
    assert "NFS-e neste mês" in html
