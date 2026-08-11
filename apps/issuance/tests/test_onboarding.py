"""Testes onboarding multi-CNPJ / multi-tenant NFS-e."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import DigitalCertificate, Tenant, TenantMembership
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.issuance.onboarding import onboard_nfse_tenant
from apps.master_data.models import Provider, ServiceCatalogItem, TaxRegime
from integrations.nfse.tests.pfx_factory import make_test_pfx


@pytest.mark.django_db
def test_onboard_nfse_tenant_idempotent(settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    pfx = make_test_pfx(password="segredo")

    first = onboard_nfse_tenant(
        slug="cliente-alpha",
        cnpj="37229907000137",
        legal_name="ALPHA TECNOLOGIA LTDA",
        user_email="admin@alpha.local",
        user_password="Secret123!",
        ibge_code="3504107",
        service_code="170101",
        fiscal_profile_name="SN-ALPHA",
        pfx_bytes=pfx,
        pfx_password="segredo",
    )
    assert first.created["tenant"] is True
    assert first.created["provider"] is True
    assert first.created["certificate"] is True
    assert first.certificate_id

    second = onboard_nfse_tenant(
        slug="cliente-alpha",
        cnpj="37229907000137",
        legal_name="ALPHA TECNOLOGIA LTDA",
        user_email="admin@alpha.local",
        ibge_code="3504107",
        service_code="170101",
        fiscal_profile_name="SN-ALPHA",
        skip_cert=True,
    )
    assert second.created["tenant"] is False
    assert second.created["provider"] is False
    assert second.created["tax_rule"] is False
    assert Tenant.objects.filter(slug="cliente-alpha").count() == 1
    assert Provider.objects.filter(tenant_id=first.tenant_id).count() == 1
    assert (
        TaxRuleCatalog.objects.filter(
            tenant_id=first.tenant_id, status=TaxRuleCatalog.Status.PUBLISHED
        ).count()
        == 1
    )
    assert MunicipalTaxRule.objects.filter(
        tenant_id=first.tenant_id, ibge_code="3504107", service_code="170101"
    ).exists()
    assert DigitalCertificate.objects.filter(
        tenant_id=first.tenant_id, cnpj="37229907000137", is_primary=True
    ).exists()


@pytest.mark.django_db
def test_onboard_second_tenant_same_service_different_cnpj(settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    onboard_nfse_tenant(
        slug="cliente-a",
        cnpj="37229907000137",
        legal_name="A LTDA",
        user_email="a@exeq.local",
        user_password="Secret123!",
        skip_cert=True,
        service_code="170101",
    )
    # CNPJ de teste distinto (válido checksum não exigido pelo onboard além de 14 dígitos
    # — validate_cnpj no create_provider). Usar outro CNPJ válido conhecido.
    from shared.validators import validate_cnpj

    cnpj_b = "00000000000191"
    validate_cnpj(cnpj_b)
    result = onboard_nfse_tenant(
        slug="cliente-b",
        cnpj=cnpj_b,
        legal_name="B LTDA",
        user_email="b@exeq.local",
        user_password="Secret123!",
        skip_cert=True,
        service_code="170101",
        fiscal_profile_name="SN-B",
    )
    assert result.created["tenant"] is True
    assert Tenant.objects.count() >= 2
    assert TenantMembership.objects.filter(tenant_id=result.tenant_id).exists()
    assert ServiceCatalogItem.objects.filter(
        tenant_id=result.tenant_id, service_code="170101"
    ).exists()
    assert FiscalProfile.objects.filter(tenant_id=result.tenant_id, name="SN-B").exists()


@pytest.mark.django_db
def test_onboard_rejects_cnpj_conflict_on_other_tenant():
    onboard_nfse_tenant(
        slug="t1",
        cnpj="37229907000137",
        legal_name="T1",
        user_email="t1@exeq.local",
        user_password="Secret123!",
        skip_cert=True,
    )
    with pytest.raises(ValueError, match="já vinculado"):
        onboard_nfse_tenant(
            slug="t2",
            cnpj="37229907000137",
            legal_name="T2",
            user_email="t2@exeq.local",
            user_password="Secret123!",
            skip_cert=True,
        )


@pytest.mark.django_db
def test_onboard_adds_rule_via_new_catalog_when_published(settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    first = onboard_nfse_tenant(
        slug="multi-ibge",
        cnpj="37229907000137",
        legal_name="MULTI LTDA",
        user_email="multi@exeq.local",
        user_password="Secret123!",
        ibge_code="3504107",
        service_code="170101",
        skip_cert=True,
    )
    second = onboard_nfse_tenant(
        slug="multi-ibge",
        cnpj="37229907000137",
        legal_name="MULTI LTDA",
        user_email="multi@exeq.local",
        ibge_code="3550308",
        municipio_nome="Sao Paulo",
        uf="SP",
        service_code="170101",
        skip_cert=True,
        iss_rate=Decimal("0.0500"),
    )
    assert second.created["tax_rule"] is True
    assert MunicipalTaxRule.objects.filter(
        tenant_id=first.tenant_id, ibge_code="3504107", service_code="170101"
    ).exists()
    assert MunicipalTaxRule.objects.filter(
        tenant_id=first.tenant_id, ibge_code="3550308", service_code="170101"
    ).exists()
    published = TaxRuleCatalog.objects.filter(
        tenant_id=first.tenant_id, status=TaxRuleCatalog.Status.PUBLISHED
    )
    assert published.count() == 1
    assert (
        MunicipalTaxRule.objects.filter(catalog=published.get()).count() >= 2
    )
