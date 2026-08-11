from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.bootstrap import ensure_published_rule
from apps.fiscal.models import FiscalProfile
from apps.fiscal.readiness import (
    FiscalReadinessError,
    assert_emit_rule_cover,
    fiscal_readiness,
    has_published_rule,
)
from apps.fiscal.templates_factory import apply_template, import_rules_csv, list_templates
from apps.fiscal.tax_engine import create_catalog, publish_catalog
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider, create_service


@pytest.fixture
def fiscal_n1_ctx(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prest N1",
        tax_regime=TaxRegime.SIMPLES,
    )
    provider.address = {"codigo_ibge": "3504107", "municipio": "Atibaia", "uf": "SP"}
    provider.save(update_fields=["address", "updated_at"])
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN-N1", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    svc_a = create_service(
        tenant=tenant_a,
        service_code="17.19",
        description="Contabilidade",
        codigo_tributacao_nacional_iss="171901",
    )
    svc_b = create_service(
        tenant=tenant_a,
        service_code="01.07",
        description="Suporte TI",
        codigo_tributacao_nacional_iss="010701",
    )
    return {
        "tenant": tenant_a,
        "provider": provider,
        "profile": profile,
        "svc_a": svc_a,
        "svc_b": svc_b,
    }


@pytest.mark.django_db
def test_n1_readiness_incomplete_without_rules(fiscal_n1_ctx):
    r = fiscal_readiness(tenant=fiscal_n1_ctx["tenant"])
    assert r.ready is False
    assert any(c.code == "coverage" and not c.ok for c in r.checks)


@pytest.mark.django_db
def test_n1_assert_blocks_and_passes(fiscal_n1_ctx):
    ctx = fiscal_n1_ctx
    with pytest.raises(FiscalReadinessError):
        assert_emit_rule_cover(
            tenant=ctx["tenant"],
            fiscal_profile=ctx["profile"],
            ibge_code="3504107",
            service_code="17.19",
        )
    ensure_published_rule(
        tenant=ctx["tenant"],
        profile=ctx["profile"],
        ibge="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="17.19",
        iss_rate=Decimal("0.0200"),
    )
    rule = assert_emit_rule_cover(
        tenant=ctx["tenant"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        service_code="17.19",
    )
    assert rule.service_code == "17.19"


@pytest.mark.django_db
def test_n2_apply_template_and_source(fiscal_n1_ctx):
    ctx = fiscal_n1_ctx
    assert any(t["id"] == "atibaia-sn-v1" for t in list_templates())
    result = apply_template(
        tenant=ctx["tenant"],
        profile=ctx["profile"],
        template_id="atibaia-sn-v1",
        service_codes=["17.19", "01.07"],
    )
    assert set(result["applied_service_codes"]) == {"17.19", "01.07"}
    assert has_published_rule(
        tenant=ctx["tenant"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        service_code="01.07",
    )
    rule = has_published_rule(
        tenant=ctx["tenant"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        service_code="17.19",
    )
    assert rule.focus_field_overrides.get("exeq_source", {}).get("kind") == "template"
    r = fiscal_readiness(tenant=ctx["tenant"])
    assert r.ready is True


@pytest.mark.django_db
def test_n2_import_csv(fiscal_n1_ctx):
    ctx = fiscal_n1_ctx
    csv_text = (
        "service_code,ibge_code,iss_rate,municipio_nome,uf\n"
        "17.19,3504107,0.02,Atibaia,SP\n"
        "01.07,3504107,0.02,Atibaia,SP\n"
    )
    result = import_rules_csv(
        tenant=ctx["tenant"], profile=ctx["profile"], csv_text=csv_text
    )
    assert len(result["applied_service_codes"]) == 2
    rule = has_published_rule(
        tenant=ctx["tenant"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        service_code="01.07",
    )
    assert rule.focus_field_overrides.get("exeq_source", {}).get("kind") == "csv"


@pytest.mark.django_db
def test_n2_template_rejects_unknown_service(fiscal_n1_ctx):
    with pytest.raises(ValueError, match="fora do template"):
        apply_template(
            tenant=fiscal_n1_ctx["tenant"],
            profile=fiscal_n1_ctx["profile"],
            template_id="atibaia-sn-v1",
            service_codes=["99.99"],
        )
