from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.models import FiscalProfile
from apps.fiscal.provision_exeq_lab import SERVICE_ROWS, provision_exeq_lab_fiscal
from apps.fiscal.readiness import (
    FiscalReadinessError,
    assert_emit_rule_cover,
    fiscal_readiness,
    has_published_rule,
)
from apps.fiscal.templates_factory import apply_template, list_templates
from apps.issuance.services import create_nf_issue, submit_nf_draft
from apps.master_data.models import Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.service_validation import normalize_ctn_iss
from apps.master_data.services import create_provider, create_service


@pytest.mark.django_db
def test_normalize_ctn_iss_requires_six_digits():
    assert normalize_ctn_iss("010701") == "010701"
    with pytest.raises(ValueError, match="6 dígitos"):
        normalize_ctn_iss("101")
    assert normalize_ctn_iss("") == ""


@pytest.mark.django_db
def test_readiness_alias_matches_lc116_when_service_code_differs(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ Lab",
        tax_regime=TaxRegime.SIMPLES,
    )
    provider.address = {"codigo_ibge": "3504107", "municipio": "Atibaia", "uf": "SP"}
    provider.save(update_fields=["address", "updated_at"])
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN-EXEQ-LAB", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    service = create_service(
        tenant=tenant_a,
        service_code="SVC-SUP-TI",
        description="Suporte TI",
        lc116_item="01.07",
        codigo_tributacao_nacional_iss="010701",
    )
    apply_template(
        tenant=tenant_a,
        profile=profile,
        template_id="exeq-lab-sn-v1",
        service_codes=["01.07"],
    )
    rule = assert_emit_rule_cover(
        tenant=tenant_a,
        fiscal_profile=profile,
        ibge_code="3504107",
        service_code=service.service_code,
        service=service,
    )
    assert rule.service_code == "01.07"
    assert has_published_rule(
        tenant=tenant_a,
        fiscal_profile=profile,
        ibge_code="3504107",
        service_code="SVC-SUP-TI",
        service=service,
    )


@pytest.mark.django_db
def test_locacao_bem_blocked_from_emit(tenant_a):
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    loc = create_service(
        tenant=tenant_a,
        service_code="OP-LOC-AUTO",
        description="Locação auto",
        operation_kind=ServiceCatalogItem.OperationKind.LOCACAO_BEM,
    )
    with pytest.raises(FiscalReadinessError, match="locação"):
        assert_emit_rule_cover(
            tenant=tenant_a,
            fiscal_profile=profile,
            ibge_code="3504107",
            service_code=loc.service_code,
            service=loc,
        )


@pytest.mark.django_db
def test_provision_exeq_lab_idempotent(tenant_a):
    tenant_a.slug = "exeq-lab-test"
    tenant_a.save(update_fields=["slug"])
    create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ Lab",
        tax_regime=TaxRegime.SIMPLES,
        address={"codigo_ibge": "3504107", "municipio": "Atibaia", "uf": "SP"},
    )
    first = provision_exeq_lab_fiscal(tenant_slug="exeq-lab-test")
    second = provision_exeq_lab_fiscal(tenant_slug="exeq-lab-test")
    assert len(first.services_created) == len(SERVICE_ROWS)
    assert second.services_created == []
    assert len(first.template_applied) == 7
    assert set(first.template_applied) == {
        "01.07",
        "01.01",
        "01.05",
        "01.06",
        "01.03",
        "10.05",
        "17.12",
    }


@pytest.mark.django_db
def test_exeq_lab_acceptance_matrix(tenant_a):
    """AC1–AC7: serviços ISS resolvem regra; locação bloqueia."""
    tenant_a.slug = "exeq-lab-ac"
    tenant_a.save(update_fields=["slug"])
    create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ Lab AC",
        tax_regime=TaxRegime.SIMPLES,
        address={"codigo_ibge": "3504107"},
    )
    provision_exeq_lab_fiscal(tenant_slug="exeq-lab-ac")
    profile = FiscalProfile.objects.get(tenant=tenant_a, name="SN-EXEQ-LAB")

    cases = [
        ("SVC-SUP-TI", "01.07", Decimal("0.0200")),
        ("SVC-DEV-ENC", "01.01", Decimal("0.0200")),
        ("SVC-SW-PAD", "01.05", Decimal("0.0200")),
        ("SVC-CONS-TI", "01.06", Decimal("0.0200")),
        ("SVC-HOST-SaaS", "01.03", Decimal("0.0200")),
        ("SVC-CORRET-IM", "10.05", Decimal("0.0500")),
        ("SVC-ADM-IM", "17.12", Decimal("0.0500")),
    ]
    for svc_code, expected_rule, expected_rate in cases:
        svc = ServiceCatalogItem.objects.get(tenant=tenant_a, service_code=svc_code)
        rule = assert_emit_rule_cover(
            tenant=tenant_a,
            fiscal_profile=profile,
            ibge_code="3504107",
            service_code=svc.service_code,
            service=svc,
        )
        assert rule.service_code == expected_rule
        assert rule.iss_rate == expected_rate

    loc = ServiceCatalogItem.objects.get(tenant=tenant_a, service_code="OP-LOC-AUTO")
    with pytest.raises(FiscalReadinessError):
        assert_emit_rule_cover(
            tenant=tenant_a,
            fiscal_profile=profile,
            ibge_code="3504107",
            service_code=loc.service_code,
            service=loc,
        )

    readiness = fiscal_readiness(tenant=tenant_a)
    assert readiness.ready is True
    assert any(t["id"] == "exeq-lab-sn-v1" for t in list_templates())


@pytest.mark.django_db
def test_submit_nf_draft_rejects_locacao_bem(tenant_a):
    from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
    from apps.issuance.models import NfIssue
    from apps.master_data.services import create_customer

    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prest",
        tax_regime=TaxRegime.SIMPLES,
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
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)
    loc = create_service(
        tenant=tenant_a,
        service_code="OP-LOC-AUTO",
        description="Locação",
        operation_kind=ServiceCatalogItem.OperationKind.LOCACAO_BEM,
    )
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="loc-block",
        provider=provider,
        customer=customer,
        service=loc,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date.today(),
        amount_cents=10000,
        descricao_servico="Locação teste",
    )
    submit_nf_draft(issue)
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.REJECTED
    assert issue.rejection_code == "OPERATION_KIND_BLOCKED"


@pytest.mark.django_db
def test_exeq_lab_dps_carries_ctn_and_simples_from_rule(tenant_a):
    from integrations.nfse.dps import to_sefin_dps_dict

    tenant_a.slug = "exeq-lab-dps"
    tenant_a.save(update_fields=["slug"])
    create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ Lab DPS",
        tax_regime=TaxRegime.SIMPLES,
        address={"codigo_ibge": "3504107"},
    )
    provision_exeq_lab_fiscal(tenant_slug="exeq-lab-dps")
    profile = FiscalProfile.objects.get(tenant=tenant_a, name="SN-EXEQ-LAB")
    provider = Provider.objects.get(tenant=tenant_a, document="37229907000137")
    from apps.master_data.services import create_customer

    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    svc = ServiceCatalogItem.objects.get(tenant=tenant_a, service_code="SVC-SUP-TI")
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="dps-ac1",
        provider=provider,
        customer=customer,
        service=svc,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date.today(),
        amount_cents=15000,
        descricao_servico="Suporte TI lab",
    )
    issue.refresh_from_db()
    params = issue.resolved_params or {}
    assert params.get("simples_codigo_tributacao") == 3
    assert params.get("iss_rate") == "0.0200"
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=99)
    inf = payload["infDPS"]
    assert inf["serv"]["cServ"]["cTribNac"] == "010701"
    assert inf["prest"]["regTrib"]["opSimpNac"] == 3
    assert "pAliq" not in inf["valores"]["trib"]["tribMun"]
