"""Sprint D — CNAEs persistidos, cTribMun Atibaia, compliance hints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.fiscal.atibaia_ctribmun import resolve_c_trib_mun
from apps.fiscal.compliance_hints import (
    provider_cnae_digits,
    service_cnae_compliance_warnings,
)
from apps.fiscal.models import FiscalProfile
from apps.fiscal.provision_exeq_lab import provision_exeq_lab_fiscal
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog, rule_to_payload
from apps.fiscal.templates_factory import apply_template
from apps.issuance.services import create_nf_issue
from apps.master_data.models import Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import apply_lookup_to_entity, create_customer, create_provider
from integrations.cadastro.port import CadastralLookupResult
from integrations.nfse.dps import to_sefin_dps_dict

SPRINT_D_SETTINGS = {
    "RTC_ENFORCE_NATIONAL_CATALOG": False,
    "NFSE_CONVENIO_HOMOLOG_IBGE_CODES": "3504107",
}


def test_resolve_c_trib_mun_atibaia_and_explicit():
    assert resolve_c_trib_mun(ibge_code="3504107", service_code="01.07") == "107"
    assert resolve_c_trib_mun(ibge_code="3504107", service_code="99.99") == ""
    assert (
        resolve_c_trib_mun(
            ibge_code="3550308", service_code="01.07", rule_c_trib_mun="999"
        )
        == "999"
    )


def test_provider_cnae_digits_from_field_and_legacy_address():
    provider = Provider(
        cnae_principal="6209100",
        cnaes_secundarios=["6201501", "6311900"],
        address={"cnaes_secundarios": ["6821801"]},
    )
    digits = provider_cnae_digits(provider)
    assert "6209100" in digits
    assert "6201501" in digits
    assert "6311900" in digits
    assert "6821801" in digits


def test_compliance_warning_when_cnae_mismatch():
    provider = Provider(cnae_principal="6920601")
    service = ServiceCatalogItem(
        service_code="SVC-SUP-TI",
        description="Suporte",
        operation_kind=ServiceCatalogItem.OperationKind.SERVICO_ISS,
    )
    warnings = service_cnae_compliance_warnings(provider=provider, service=service)
    assert len(warnings) == 1
    assert "6209100" in warnings[0]


def test_compliance_ok_when_cnae_matches():
    provider = Provider(cnae_principal="6209100")
    service = ServiceCatalogItem(
        service_code="SVC-SUP-TI",
        description="Suporte",
        operation_kind=ServiceCatalogItem.OperationKind.SERVICO_ISS,
    )
    assert service_cnae_compliance_warnings(provider=provider, service=service) == []


def test_compliance_ok_when_cnae_prefix_matches():
    provider = Provider(cnae_principal="6209101")
    service = ServiceCatalogItem(
        service_code="SVC-SUP-TI",
        description="Suporte",
        operation_kind=ServiceCatalogItem.OperationKind.SERVICO_ISS,
    )
    assert service_cnae_compliance_warnings(provider=provider, service=service) == []


def test_compliance_no_hints_for_unknown_service():
    provider = Provider(cnae_principal="6920601")
    service = ServiceCatalogItem(
        service_code="SVC-UNKNOWN",
        description="Outro",
        operation_kind=ServiceCatalogItem.OperationKind.SERVICO_ISS,
    )
    assert service_cnae_compliance_warnings(provider=provider, service=service) == []


def test_compliance_warns_when_provider_has_no_cnae():
    provider = Provider(cnae_principal="")
    service = ServiceCatalogItem(
        service_code="SVC-SUP-TI",
        description="Suporte",
        operation_kind=ServiceCatalogItem.OperationKind.SERVICO_ISS,
    )
    warnings = service_cnae_compliance_warnings(provider=provider, service=service)
    assert len(warnings) == 1
    assert "não cadastrado" in warnings[0]


def test_normalize_cnae_digits_strips_non_digits():
    from apps.fiscal.compliance_hints import normalize_cnae_digits

    assert normalize_cnae_digits("62.09-1/00") == "6209100"


def test_cnae_matches_empty_hint():
    from apps.fiscal.compliance_hints import _cnae_matches

    assert _cnae_matches({"6209100"}, "") is True


@pytest.mark.django_db
@override_settings(**SPRINT_D_SETTINGS)
def test_submit_persists_compliance_hints_soft(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Prest",
        tax_regime=TaxRegime.SIMPLES,
        cnae_principal="6920601",
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    service = ServiceCatalogItem.objects.create(
        tenant=tenant_a,
        service_code="SVC-SUP-TI",
        description="Suporte",
        lc116_item="01.07",
        codigo_tributacao_nacional_iss="010701",
        is_active=True,
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="01.07",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
        c_trib_mun="107",
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)

    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="hints-soft",
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date.today(),
        amount_cents=10000,
        descricao_servico="Suporte",
    )
    issue.refresh_from_db()
    hints = issue.resolved_params.get("compliance_hints") or []
    assert hints
    assert issue.status != "rejected"


def test_compliance_skips_locacao():
    provider = Provider(cnae_principal="7711000")
    service = ServiceCatalogItem(
        service_code="OP-LOC-AUTO",
        description="Locação",
        operation_kind=ServiceCatalogItem.OperationKind.LOCACAO_BEM,
    )
    assert service_cnae_compliance_warnings(provider=provider, service=service) == []


@pytest.mark.django_db
def test_apply_lookup_persists_cnaes_secundarios(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ",
        tax_regime=TaxRegime.SIMPLES,
    )
    result = CadastralLookupResult(
        document="37229907000137",
        legal_name="EXEQ LAB",
        cnae_principal="6209100",
        cnaes_secundarios=["6201501", "6311900"],
    )
    apply_lookup_to_entity(provider, result)
    provider.refresh_from_db()
    assert provider.cnaes_secundarios == ["6201501", "6311900"]


@pytest.mark.django_db
def test_template_exeq_lab_sets_c_trib_mun(tenant_a):
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN-D", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    apply_template(tenant=tenant_a, profile=profile, template_id="exeq-lab-sn-v1")
    from apps.fiscal.models import MunicipalTaxRule, TaxRuleCatalog

    published = TaxRuleCatalog.objects.get(tenant=tenant_a, status="published")
    rule = MunicipalTaxRule.objects.get(
        catalog=published, service_code="01.07", ibge_code="3504107"
    )
    assert rule.c_trib_mun == "107"
    payload = rule_to_payload(rule)
    assert payload["c_trib_mun"] == "107"


@pytest.mark.django_db
@override_settings(**SPRINT_D_SETTINGS)
def test_dps_includes_c_trib_mun_from_resolved_params(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Prest",
        tax_regime=TaxRegime.SIMPLES,
        cnae_principal="6209100",
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    service = ServiceCatalogItem.objects.create(
        tenant=tenant_a,
        service_code="SVC-SUP-TI",
        description="Suporte",
        lc116_item="01.07",
        codigo_tributacao_nacional_iss="010701",
        is_active=True,
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="01.07",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
        c_trib_mun="107",
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)

    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="dps-ctrib",
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date.today(),
        amount_cents=10000,
        descricao_servico="Suporte",
    )
    issue.refresh_from_db()
    assert issue.resolved_params.get("c_trib_mun") == "107"
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=1)
    assert payload["infDPS"]["serv"]["cServ"]["cTribMun"] == "107"


@pytest.mark.django_db
@override_settings(**SPRINT_D_SETTINGS)
def test_provision_persists_cnaes_on_provider(tenant_a):
    tenant_a.slug = "exeq-lab-d"
    tenant_a.save(update_fields=["slug"])
    create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ",
        tax_regime=TaxRegime.SIMPLES,
        address={"codigo_ibge": "3504107"},
    )
    provision_exeq_lab_fiscal(tenant_slug="exeq-lab-d")
    provider = Provider.objects.get(tenant=tenant_a, document="37229907000137")
    assert provider.cnae_principal == "6209100"
    assert "6201501" in provider.cnaes_secundarios
    assert len(provider.cnaes_secundarios) >= 8
