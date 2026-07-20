from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from integrations.nfse.mappers import to_focus_nfse, to_focus_nfsen


@pytest.fixture
def emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador ACME",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="12345",
        address={"logradouro": "Rua A", "numero": "10", "uf": "SP", "cep": "12940-000"},
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente Silva",
        email="cliente@exeq.local",
        address={
            "logradouro": "Rua B",
            "numero": "20",
            "bairro": "Centro",
            "uf": "SP",
            "cep": "12940-001",
            "codigo_municipio": "3504107",
        },
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
        iss_retained=False,
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
def test_to_focus_nfsen_flat_payload(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="payload-nfsen-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=15050,
    )
    issue.refresh_from_db()
    body = issue.internal_payload or to_focus_nfsen(issue)

    assert body["cnpj_prestador"] == "00000000000191"
    assert body["cpf_tomador"] == "52998224725"
    assert str(body["codigo_municipio_emissora"]) == "3504107"
    assert body["codigo_municipio_prestacao"] == "3504107"
    assert body["valor_servico"] == 150.5
    assert body["codigo_tributacao_nacional_iss"] == "1.01"
    assert body["codigo_opcao_simples_nacional"] == 3
    assert body["tipo_retencao_iss"] == 1
    assert "percentual_aliquota_relativa_municipio" not in body
    assert "indicador_total_tributacao" not in body
    assert body["percentual_total_tributos_simples_nacional"] == 6.0
    assert body["data_competencia"] == "2024-06-15"
    assert "prestador" not in body


@pytest.mark.django_db
def test_to_focus_nfsen_prefers_codigo_tributacao_nacional(tenant_a, emission_setup):
    emission_setup["service"].codigo_tributacao_nacional_iss = "010101"
    emission_setup["service"].save(update_fields=["codigo_tributacao_nacional_iss"])
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="payload-nfsen-code",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    body = to_focus_nfsen(issue)
    assert body["codigo_tributacao_nacional_iss"] == "010101"


@pytest.mark.django_db
def test_to_focus_nfse_nested_payload(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="payload-nfse-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    body = to_focus_nfse(issue)
    assert body["prestador"]["cnpj"] == "00000000000191"
    assert body["tomador"]["cpf"] == "52998224725"
    assert body["servico"]["valor_servicos"] == 100.0
    assert body["servico"]["aliquota"] == 2.0
