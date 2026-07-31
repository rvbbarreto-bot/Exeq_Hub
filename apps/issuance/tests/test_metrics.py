"""Testes KPIs piloto NFS-e (M5)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.metrics import compute_nfse_piloto_kpis
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


@pytest.fixture
def emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Serviço",
        codigo_tributacao_nacional_iss="010101",
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
    return {
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_compute_nfse_piloto_kpis_happy_path(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="kpi-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=1000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED
    report = compute_nfse_piloto_kpis(tenant_id=tenant_a.id)
    assert report["total_issues"] >= 1
    assert report["authorization_rate"] == 1.0
    assert report["happy_path_no_poll_rate"] == 1.0
    assert report["certificates_expiring_or_expired"] >= 0
