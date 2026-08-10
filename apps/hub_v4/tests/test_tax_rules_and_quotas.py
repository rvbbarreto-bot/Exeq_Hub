"""Regras municipais Hub + quotas max_users / max_nf_month."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.membership_services import ensure_membership
from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.plan_limits import (
    PlanLimitError,
    assert_can_add_active_user,
    max_nf_month,
    max_users,
    provider_usage,
)
from apps.accounts.plan_services import assign_plan, ensure_system_plans
from apps.accounts.services import ensure_system_roles
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


@pytest.fixture
def hub_rules_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    ensure_system_plans()
    tenant = Tenant.objects.create(
        slug="rules-hub-qa",
        legal_name="Rules Hub QA",
        document="34028316000103",
    )
    user = User.objects.create_user(
        email="rules.hub@exeq.local", password="Secret123!", name="Rules Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    return tenant, user, roles, profile


def _login(client, tenant, user):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_tax_rules_list_and_create(client, hub_rules_ctx):
    tenant, user, _roles, profile = hub_rules_ctx
    _login(client, tenant, user)
    r = client.get(reverse("hub-v4-tax-rules"))
    assert r.status_code == 200
    assert b"Regras" in r.content or b"municipal" in r.content.lower()

    r = client.post(
        reverse("hub-v4-tax-rule-new"),
        {
            "fiscal_profile_id": str(profile.id),
            "ibge_code": "3504107",
            "municipio_nome": "Atibaia",
            "uf": "SP",
            "service_code": "17.19",
            "iss_rate": "0.03",
        },
    )
    assert r.status_code == 302
    published = TaxRuleCatalog.objects.get(
        tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
    )
    rule = MunicipalTaxRule.objects.get(catalog=published, service_code="17.19")
    assert rule.iss_rate == Decimal("0.0300")
    assert rule.fiscal_profile_id == profile.id


@pytest.mark.django_db
def test_max_users_enforcement(hub_rules_ctx):
    tenant, user, roles, _profile = hub_rules_ctx
    plan = ensure_system_plans()
    assign_plan(tenant=tenant, plan="starter")  # max_users=2
    assert max_users(tenant) == 2
    # already 1 (fixture)
    u2 = User.objects.create_user(email="u2@exeq.local", password="Secret123!")
    ensure_membership(tenant=tenant, user=u2, role=roles["operator"], is_active=True)
    assert TenantMembership.objects.filter(tenant=tenant, is_active=True).count() == 2
    u3 = User.objects.create_user(email="u3@exeq.local", password="Secret123!")
    with pytest.raises(PlanLimitError):
        assert_can_add_active_user(tenant)
    with pytest.raises(PlanLimitError):
        ensure_membership(tenant=tenant, user=u3, role=roles["readonly"], is_active=True)


@pytest.mark.django_db
def test_max_nf_month_blocks_create(tenant_a):
    ensure_system_plans()
    tenant_a.settings = {"max_nf_month": 1}
    tenant_a.save(update_fields=["settings"])
    assert max_nf_month(tenant_a) == 1

    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="P",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="C",
    )
    service = create_service(
        tenant=tenant_a, service_code="1.01", description="S", codigo_tributacao_nacional_iss="010101"
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.02"),
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)

    kwargs = dict(
        tenant=tenant_a,
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date.today(),
        amount_cents=10000,
    )
    create_nf_issue(idempotency_key="nf-quota-1", **kwargs)
    assert NfIssue.objects.filter(tenant=tenant_a).count() == 1
    with pytest.raises(PlanLimitError):
        create_nf_issue(idempotency_key="nf-quota-2", **kwargs)
    # idempotent same key still works
    again = create_nf_issue(idempotency_key="nf-quota-1", **kwargs)
    assert again.idempotency_key == "nf-quota-1"

    usage = provider_usage(tenant_a)
    assert usage["nf_month"]["at_limit"] is True
    assert usage["nf_month"]["used"] == 1
