"""Dashboard — KPI Certificados da empresa em uso."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.certificates import upload_a1_certificate
from apps.accounts.models import DigitalCertificate, Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.hub_v4.services import certificate_kpi
from apps.hub_v4.tests.test_certificates_hub import _make_pfx, _login
from apps.master_data.models import Provider, TaxRegime


@pytest.fixture
def dash_cert_ctx(db, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="dash-cert-qa",
        legal_name="Dash Cert QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="dash.cert@exeq.local", password="Secret123!", name="Dash Cert"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="04252011000110",
        legal_name="Empresa KPI SA",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
    )
    return tenant, user, provider


def _upload(client, tenant, user, provider, *, days: int = 60):
    _login(client, tenant, user)
    from django.core.files.uploadedfile import SimpleUploadedFile

    pfx = _make_pfx(days=days)
    upload = SimpleUploadedFile("a1.pfx", pfx, content_type="application/x-pkcs12")
    client.post(
        reverse("hub-v4-certificates"),
        {
            "provider_id": str(provider.id),
            "label": "A1 KPI",
            "password": "secret",
            "make_primary": "1",
            "file": upload,
        },
    )


@pytest.mark.django_db
def test_certificate_kpi_no_cert_shows_zero_ativos(dash_cert_ctx):
    tenant, _, provider = dash_cert_ctx
    kpi = certificate_kpi(tenant, cnpj=provider.document)
    assert kpi["value"] == 0
    assert kpi["hint"] == "ativos"
    assert kpi["tone"] == "total"
    assert kpi["status"] is False


@pytest.mark.django_db
def test_certificate_kpi_expired(dash_cert_ctx, tmp_path, settings):
    tenant, user, provider = dash_cert_ctx
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    upload_a1_certificate(
        tenant=tenant,
        label="A1",
        cnpj=provider.document,
        pfx_bytes=_make_pfx(days=60),
        password="secret",
        provider=provider,
    )
    cert = DigitalCertificate.objects.get(tenant=tenant, cnpj=provider.document)
    cert.not_after = timezone.now() - timedelta(days=5)
    cert.status = DigitalCertificate.Status.EXPIRED
    cert.save(update_fields=["not_after", "status", "updated_at"])

    kpi = certificate_kpi(tenant, cnpj=provider.document)
    assert kpi["value"] == "Expirado há 5 dias"
    assert kpi["tone"] == "err"
    assert kpi["status"] is True


@pytest.mark.django_db
def test_certificate_kpi_expiring_in_30_days(dash_cert_ctx, tmp_path, settings):
    tenant, _, provider = dash_cert_ctx
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    upload_a1_certificate(
        tenant=tenant,
        label="A1",
        cnpj=provider.document,
        pfx_bytes=_make_pfx(days=60),
        password="secret",
        provider=provider,
    )
    cert = DigitalCertificate.objects.get(tenant=tenant, cnpj=provider.document)
    cert.not_after = timezone.localdate() + timedelta(days=30)
    cert.save(update_fields=["not_after", "updated_at"])

    kpi = certificate_kpi(tenant, cnpj=provider.document)
    assert kpi["value"] == "Expira em 30 dias"
    assert kpi["tone"] == "warn"
    assert kpi["status"] is True


@pytest.mark.django_db
def test_dashboard_renders_certificate_kpi(client, dash_cert_ctx):
    tenant, user, provider = dash_cert_ctx
    _upload(client, tenant, user, provider, days=60)
    cert = DigitalCertificate.objects.get(tenant=tenant, cnpj=provider.document)
    cert.not_after = timezone.localdate() + timedelta(days=30)
    cert.save(update_fields=["not_after", "updated_at"])

    html = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert "Expira em 30 dias" in html
    assert "metric-warn" in html
    assert "metric-status" in html
