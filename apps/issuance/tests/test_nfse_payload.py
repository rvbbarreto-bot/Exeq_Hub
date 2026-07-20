"""Compat tests — mappers oficiais em integrations.nfse.tests.test_mappers."""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.nfse_payload import build_focus_nfse_body
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


@pytest.fixture
def emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador ACME",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="12345",
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente Silva",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Desenvolvimento de software",
        lc116_item="1.01",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN",
        tax_regime=TaxRegime.SIMPLES,
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
        iss_rate=Decimal("0.0200"),
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)
    return {
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_build_focus_nfse_body_maps_parties(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="payload-compat-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=15050,
    )
    nested = build_focus_nfse_body(issue)
    assert nested["prestador"]["cnpj"] == "00000000000191"
    assert issue.internal_payload["cnpj_prestador"] == "00000000000191"
