"""Perfis fiscais + serviços no Hub; bootstrap de regra municipal."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.fiscal.bootstrap import ensure_published_rule
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.master_data.models import ServiceCatalogItem, TaxRegime


@pytest.fixture
def hub_fiscal_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="fiscal-hub-qa",
        legal_name="Fiscal Hub QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="fiscal.hub@exeq.local", password="Secret123!", name="Fiscal Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    return tenant, user


def _login(client, tenant, user):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_ensure_published_rule_idempotent(tenant_a):
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    c1 = ensure_published_rule(
        tenant=tenant_a,
        profile=profile,
        ibge="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="17.19",
        iss_rate=Decimal("0.02"),
    )
    assert c1.status == TaxRuleCatalog.Status.PUBLISHED
    assert MunicipalTaxRule.objects.filter(catalog=c1, service_code="17.19").exists()
    c2 = ensure_published_rule(
        tenant=tenant_a,
        profile=profile,
        ibge="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="17.19",
        iss_rate=Decimal("0.02"),
    )
    assert c2.id == c1.id
    assert TaxRuleCatalog.objects.filter(tenant=tenant_a).count() == 1


@pytest.mark.django_db
def test_hub_create_fiscal_profile_with_rule(client, hub_fiscal_ctx):
    tenant, user = hub_fiscal_ctx
    _login(client, tenant, user)
    r = client.post(
        reverse("hub-v4-fiscal-new"),
        {
            "name": "Simples Escritório",
            "tax_regime": TaxRegime.SIMPLES,
            "status": "active",
            "iss_retention_policy": "by_rule",
            "ensure_rule": "1",
            "ibge_code": "3504107",
            "municipio_nome": "Atibaia",
            "uf": "SP",
            "rule_service_code": "17.19",
            "iss_rate": "0.02",
        },
    )
    assert r.status_code == 302
    profile = FiscalProfile.objects.get(tenant=tenant, name="Simples Escritório")
    published = TaxRuleCatalog.objects.get(
        tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
    )
    assert MunicipalTaxRule.objects.filter(
        catalog=published, fiscal_profile=profile, service_code="17.19"
    ).exists()


@pytest.mark.django_db
def test_hub_service_create_and_seed(client, hub_fiscal_ctx):
    tenant, user = hub_fiscal_ctx
    _login(client, tenant, user)
    r = client.get(reverse("hub-v4-services"))
    assert r.status_code == 200
    assert b"Servi" in r.content

    r = client.post(
        reverse("hub-v4-service-new"),
        {
            "service_code": "17.19",
            "description": "Contabilidade",
            "lc116_item": "17.19",
            "codigo_tributacao_nacional_iss": "",
            "is_active": "1",
        },
    )
    assert r.status_code == 302
    assert ServiceCatalogItem.objects.filter(
        tenant=tenant, service_code="17.19"
    ).exists()

    r = client.post(reverse("hub-v4-services-materialize"))
    assert r.status_code == 302
    # Without national pack, seeds minimum catalog
    assert ServiceCatalogItem.objects.filter(tenant=tenant).count() >= 1


@pytest.mark.django_db
def test_hub_nav_fiscal_services(client, hub_fiscal_ctx):
    tenant, user = hub_fiscal_ctx
    _login(client, tenant, user)
    html = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert "Perfis fiscais" in html
    assert "Serviços" in html
    assert reverse("hub-v4-fiscal") in html or "/hub/fiscal/" in html
