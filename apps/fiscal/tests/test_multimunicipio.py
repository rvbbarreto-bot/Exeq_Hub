"""Sprint C — multimunicípio: IBGE + CSV multi-IBGE."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings

SPRINT_C_TEST_SETTINGS = {
    "RTC_ENFORCE_NATIONAL_CATALOG": False,
    "NFSE_CONVENIO_HOMOLOG_IBGE_CODES": "3504107,3550308",
}

from apps.fiscal.models import FiscalProfile
from apps.fiscal.multimunicipio import (
    list_published_ibge_codes,
    normalize_ibge_code,
    parse_csv_preview,
    provider_default_ibge,
    resolve_wizard_ibge_code,
)
from apps.fiscal.provision_exeq_lab import provision_exeq_lab_fiscal
from apps.fiscal.readiness import assert_emit_rule_cover
from apps.fiscal.templates_factory import import_rules_csv
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import create_customer, create_provider


@pytest.fixture
def multimunicipio_ctx(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ Lab",
        tax_regime=TaxRegime.SIMPLES,
        address={"codigo_ibge": "3504107", "municipio": "Atibaia", "uf": "SP"},
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN-MULTI", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    return {"tenant": tenant_a, "provider": provider, "profile": profile}


def test_normalize_ibge_code_valid_and_invalid():
    assert normalize_ibge_code("3504107") == "3504107"
    assert normalize_ibge_code("35.041.07") == "3504107"
    with pytest.raises(ValueError, match="7 dígitos"):
        normalize_ibge_code("35041")
    with pytest.raises(ValueError, match="7 dígitos"):
        normalize_ibge_code("")


def test_provider_default_ibge(multimunicipio_ctx):
    assert provider_default_ibge(multimunicipio_ctx["provider"]) == "3504107"


def test_resolve_wizard_ibge_explicit_over_provider(multimunicipio_ctx):
    ibge = resolve_wizard_ibge_code(
        post_ibge="3550308",
        provider=multimunicipio_ctx["provider"],
    )
    assert ibge == "3550308"


def test_resolve_wizard_ibge_falls_back_to_provider(multimunicipio_ctx):
    ibge = resolve_wizard_ibge_code(
        post_ibge="",
        provider=multimunicipio_ctx["provider"],
    )
    assert ibge == "3504107"


def test_resolve_wizard_ibge_not_required():
    provider = Provider(
        document="00000000000191",
        legal_name="Sem IBGE",
        tax_regime=TaxRegime.SIMPLES,
        address={},
    )
    assert resolve_wizard_ibge_code(post_ibge="", provider=provider, required=False) == ""


def test_resolve_wizard_ibge_required_when_missing():
    provider = Provider(
        document="00000000000191",
        legal_name="Sem IBGE",
        tax_regime=TaxRegime.SIMPLES,
        address={},
    )
    with pytest.raises(ValueError, match="Informe o IBGE"):
        resolve_wizard_ibge_code(post_ibge="", provider=provider)


def test_parse_csv_preview_validates_ibge(multimunicipio_ctx):
    csv_text = (
        "service_code,ibge_code,iss_rate\n"
        "01.07,3504107,0.02\n"
        "01.07,355,0.05\n"
    )
    with pytest.raises(ValueError, match="Linha 3"):
        parse_csv_preview(csv_text)


def test_import_rules_csv_multi_ibge(multimunicipio_ctx):
    ctx = multimunicipio_ctx
    csv_text = (
        "service_code,ibge_code,iss_rate,municipio_nome,uf\n"
        "01.07,3504107,0.02,Atibaia,SP\n"
        "01.07,3550308,0.05,São Paulo,SP\n"
    )
    result = import_rules_csv(tenant=ctx["tenant"], profile=ctx["profile"], csv_text=csv_text)
    assert len(result["applied_service_codes"]) == 2
    assert set(result["ibge_codes"]) == {"3504107", "3550308"}
    assert len(result["applied_rows"]) == 2


def test_list_published_ibge_codes(multimunicipio_ctx):
    ctx = multimunicipio_ctx
    csv_text = (
        "service_code,ibge_code,iss_rate\n"
        "01.07,3504107,0.02\n"
        "01.07,3550308,0.05\n"
    )
    import_rules_csv(tenant=ctx["tenant"], profile=ctx["profile"], csv_text=csv_text)
    codes = list_published_ibge_codes(tenant=ctx["tenant"])
    ibges = {c["ibge_code"] for c in codes}
    assert "3504107" in ibges
    assert "3550308" in ibges


@pytest.mark.django_db
@override_settings(**SPRINT_C_TEST_SETTINGS)
def test_ac8_emit_sp_ibge_after_csv_import(multimunicipio_ctx):
    """AC8: serviço com regra SP quando CSV multimunicípio importado."""
    ctx = multimunicipio_ctx
    tenant_a = ctx["tenant"]
    tenant_a.slug = "exeq-lab-sp"
    tenant_a.save(update_fields=["slug"])

    service = ServiceCatalogItem.objects.create(
        tenant=tenant_a,
        service_code="SVC-SUP-TI",
        description="Suporte TI",
        lc116_item="01.07",
        codigo_tributacao_nacional_iss="010701",
        is_active=True,
    )
    csv_text = (
        "service_code,ibge_code,iss_rate,municipio_nome,uf\n"
        "01.07,3504107,0.02,Atibaia,SP\n"
        "01.07,3550308,0.05,São Paulo,SP\n"
    )
    import_rules_csv(tenant=tenant_a, profile=ctx["profile"], csv_text=csv_text)

    rule = assert_emit_rule_cover(
        tenant=tenant_a,
        fiscal_profile=ctx["profile"],
        ibge_code="3550308",
        service_code=service.service_code,
        service=service,
    )
    assert rule.ibge_code == "3550308"
    assert rule.iss_rate == Decimal("0.0500")

    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente SP",
    )
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="ac8-sp",
        provider=ctx["provider"],
        customer=customer,
        service=service,
        fiscal_profile=ctx["profile"],
        ibge_code="3550308",
        competence_date=date.today(),
        amount_cents=20000,
        descricao_servico="Suporte em SP",
    )
    issue.refresh_from_db()
    assert issue.ibge_code == "3550308"
    assert issue.status != NfIssue.Status.REJECTED


@pytest.mark.django_db
def test_exeq_lab_provision_plus_sp_csv(multimunicipio_ctx):
    tenant_a = multimunicipio_ctx["tenant"]
    tenant_a.slug = "exeq-lab-multi"
    tenant_a.save(update_fields=["slug"])
    provision_exeq_lab_fiscal(tenant_slug="exeq-lab-multi")
    profile = FiscalProfile.objects.get(tenant=tenant_a, name="SN-EXEQ-LAB")
    csv_text = "service_code,ibge_code,iss_rate\n01.07,3550308,0.05\n"
    result = import_rules_csv(tenant=tenant_a, profile=profile, csv_text=csv_text)
    assert "3550308" in result["ibge_codes"]
    svc = ServiceCatalogItem.objects.get(tenant=tenant_a, service_code="SVC-SUP-TI")
    rule = assert_emit_rule_cover(
        tenant=tenant_a,
        fiscal_profile=profile,
        ibge_code="3550308",
        service_code=svc.service_code,
        service=svc,
    )
    assert rule.iss_rate == Decimal("0.0500")
