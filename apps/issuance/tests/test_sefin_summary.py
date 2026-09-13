from datetime import date

import pytest

from apps.fiscal.models import FiscalProfile
from apps.issuance.models import NfIssue
from apps.issuance.sefin_summary import sefin_integration_summary
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
    return {
        "tenant": tenant_a,
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_sefin_summary_authorized_from_raw(emission_setup):
    issue = NfIssue.objects.create(
        tenant=emission_setup["tenant"],
        idempotency_key="sefin-sum-1",
        status=NfIssue.Status.AUTHORIZED,
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 10),
        amount_cents=1191,
        focus_ref="35041072237229907000137000000000007326089164550900",
        focus_status_raw={
            "provider": "sefin",
            "mode": "http",
            "http_status": 201,
            "tipoAmbiente": 1,
            "chaveAcesso": "35041072237229907000137000000000007326089164550900",
            "versaoAplicativo": "SefinNacional_1.6.0",
            "xml": (
                '<?xml version="1.0"?><NFSe><infNFSe>'
                "<nNFSe>73</nNFSe><cStat>100</cStat><ambGer>2</ambGer>"
                "<verAplic>SefinNacional_1.6.0</verAplic>"
                "<DPS><infDPS><tpAmb>1</tpAmb></infDPS></DPS>"
                "</infNFSe></NFSe>"
            ),
        },
    )
    s = sefin_integration_summary(issue)
    assert s["integrated"] is True
    assert s["n_nfse"] == "73"
    assert s["c_stat"] == "100"
    assert s["chave_acesso"].startswith("3504107")
    assert s["ambiente_label"] == "produção"


@pytest.mark.django_db
def test_sefin_summary_local_reject(emission_setup):
    issue = NfIssue.objects.create(
        tenant=emission_setup["tenant"],
        idempotency_key="sefin-sum-2",
        status=NfIssue.Status.REJECTED,
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 10),
        amount_cents=1900,
        rejection_code="TAX_RULE_NOT_FOUND",
    )
    s = sefin_integration_summary(issue)
    assert s["integrated"] is False
    assert s["reject_local"] is True
