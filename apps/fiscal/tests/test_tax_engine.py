from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.exceptions import PublishChecklistIncompleteError, TaxRuleNotFoundError
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import (
    add_rule,
    create_catalog,
    publish_catalog,
    resolve_tax_rule,
)


@pytest.fixture
def fiscal_profile(tenant_a):
    return FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN",
        tax_regime="simples_nacional",
    )


@pytest.mark.django_db
def test_publish_requires_checklist(tenant_a, fiscal_profile):
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=fiscal_profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime="simples_nacional",
        iss_rate=Decimal("0.0200"),
        iss_retained=False,
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
    )
    with pytest.raises(PublishChecklistIncompleteError) as exc:
        publish_catalog(catalog)
    assert "csv_validated" in exc.value.missing


@pytest.mark.django_db
def test_publish_supersedes_previous_and_resolve_atibaia(tenant_a, fiscal_profile):
    old = create_catalog(tenant=tenant_a)
    old.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    old.save(update_fields=["publish_checklist"])
    publish_catalog(old)

    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=fiscal_profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime="simples_nacional",
        iss_rate=Decimal("0.0200"),
        iss_retained=False,
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
        priority=10,
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)

    old.refresh_from_db()
    assert old.status == "superseded"
    catalog.refresh_from_db()
    assert catalog.status == "published"

    rule = resolve_tax_rule(
        tenant=tenant_a,
        fiscal_profile=fiscal_profile,
        ibge_code="3504107",
        service_code="1.01",
        tax_regime="simples_nacional",
        competence_date=date(2024, 6, 15),
    )
    assert rule.iss_rate == Decimal("0.0200")
    assert rule.simples_codigo_tributacao == 3


@pytest.mark.django_db
def test_resolve_without_rule_raises(tenant_a, fiscal_profile):
    catalog = create_catalog(tenant=tenant_a)
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)
    with pytest.raises(TaxRuleNotFoundError):
        resolve_tax_rule(
            tenant=tenant_a,
            fiscal_profile=fiscal_profile,
            ibge_code="3550308",
            service_code="1.01",
            tax_regime="simples_nacional",
            competence_date=date(2024, 6, 15),
        )


@pytest.mark.django_db
def test_tax_resolve_api(api_client, auth_header, tenant_a, fiscal_profile):
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=fiscal_profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime="simples_nacional",
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

    response = api_client.post(
        "/api/v1/tax/resolve",
        {
            "fiscal_profile_id": str(fiscal_profile.id),
            "ibge_code": "3504107",
            "service_code": "1.01",
            "tax_regime": "simples_nacional",
            "competence_date": "2024-06-15",
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 200
    assert response.data["iss_rate"] == "0.0200"
    assert response.data["simples_codigo_tributacao"] == 3
