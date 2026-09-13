"""Plan + Subscription enforce max_emit_cnpjs."""

from __future__ import annotations

import pytest

from apps.accounts.models import Subscription, Tenant
from apps.accounts.plan_limits import (
    PlanLimitError,
    assert_can_add_active_provider,
    max_emit_cnpjs,
    provider_usage,
)
from apps.accounts.plan_services import assign_plan, ensure_system_plans
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider


@pytest.mark.django_db
def test_ensure_system_plans_seed():
    plans = ensure_system_plans()
    codes = {p.code for p in plans}
    assert {"starter", "contabil_5", "contabil_20", "enterprise"} <= codes
    # idempotente
    again = ensure_system_plans()
    assert len(again) == len(plans)


@pytest.mark.django_db
def test_subscription_enforces_max_emit_cnpjs():
    ensure_system_plans()
    tenant = Tenant.objects.create(
        slug="sub-plan-qa",
        legal_name="Sub Plan QA",
        document="34028316000103",
        settings={},
    )
    assert max_emit_cnpjs(tenant) is None
    assign_plan(tenant=tenant, plan="contabil_5")
    assert max_emit_cnpjs(tenant) == 5
    usage = provider_usage(tenant)
    assert usage["plan_code"] == "contabil_5"
    assert usage["source"] == "subscription"
    assert usage["plan_name"] == "Contábil 5"

    for i, doc in enumerate(
        ("04252011000110", "00000000000191", "11444777000161", "11222333000181")
    ):
        create_provider(
            tenant=tenant,
            document=doc,
            legal_name=f"Emp {i}",
            tax_regime=TaxRegime.SIMPLES,
        )
    create_provider(
        tenant=tenant,
        document="00000000000272",
        legal_name="Emp 5",
        tax_regime=TaxRegime.SIMPLES,
    )
    assert max_emit_cnpjs(tenant) == 5
    assert provider_usage(tenant)["at_limit"] is True
    with pytest.raises(PlanLimitError):
        assert_can_add_active_provider(tenant)


@pytest.mark.django_db
def test_settings_override_beats_subscription():
    ensure_system_plans()
    tenant = Tenant.objects.create(
        slug="override-qa",
        legal_name="Override QA",
        document="00000000000272",
        settings={"max_emit_cnpjs": 1},
    )
    assign_plan(tenant=tenant, plan="contabil_20")
    assert max_emit_cnpjs(tenant) == 1
    assert provider_usage(tenant)["source"] == "settings_override"


@pytest.mark.django_db
def test_canceled_subscription_ignored():
    ensure_system_plans()
    tenant = Tenant.objects.create(
        slug="canceled-qa",
        legal_name="Canceled QA",
        document="00000000000191",
    )
    sub = assign_plan(tenant=tenant, plan="starter")
    sub.status = Subscription.Status.CANCELED
    sub.save(update_fields=["status"])
    assert max_emit_cnpjs(tenant) is None
