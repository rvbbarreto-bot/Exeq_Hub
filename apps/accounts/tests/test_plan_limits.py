"""Limite de CNPJs emitentes (tenant.settings.max_emit_cnpjs)."""

from __future__ import annotations

import pytest

from apps.accounts.models import Tenant
from apps.accounts.plan_limits import (
    PlanLimitError,
    assert_can_add_active_provider,
    can_add_active_provider,
    max_emit_cnpjs,
    provider_usage,
)
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider


@pytest.fixture
def tenant_limited(db):
    return Tenant.objects.create(
        slug="limit-qa",
        legal_name="Limit QA Contábil",
        document="11222333000181",
        settings={"max_emit_cnpjs": 2},
    )


@pytest.mark.django_db
def test_max_emit_cnpjs_reads_settings(tenant_limited):
    assert max_emit_cnpjs(tenant_limited) == 2
    tenant_limited.settings = {}
    assert max_emit_cnpjs(tenant_limited) is None


@pytest.mark.django_db
def test_create_provider_enforces_plan_limit(tenant_limited):
    create_provider(
        tenant=tenant_limited,
        document="04.252.011/0001-10",
        legal_name="Empresa Um",
        tax_regime=TaxRegime.SIMPLES,
    )
    create_provider(
        tenant=tenant_limited,
        document="00.000.000/0001-91",
        legal_name="Empresa Dois",
        tax_regime=TaxRegime.SIMPLES,
    )
    usage = provider_usage(tenant_limited)
    assert usage["used"] == 2
    assert usage["at_limit"] is True
    assert can_add_active_provider(tenant_limited) is False

    with pytest.raises(PlanLimitError):
        assert_can_add_active_provider(tenant_limited)

    with pytest.raises(PlanLimitError):
        create_provider(
            tenant=tenant_limited,
            document="11.444.777/0001-61",
            legal_name="Empresa Três",
            tax_regime=TaxRegime.SIMPLES,
        )

    # Inativo não ocupa slot
    create_provider(
        tenant=tenant_limited,
        document="11.444.777/0001-61",
        legal_name="Empresa Três Inativa",
        tax_regime=TaxRegime.SIMPLES,
        is_active=False,
    )
    assert provider_usage(tenant_limited)["used"] == 2
