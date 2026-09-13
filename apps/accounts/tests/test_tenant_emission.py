"""Flags de emissão por tenant (NFS-e / NF-e)."""

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.admin_tenant_forms import TenantAdminForm
from apps.accounts.models import Tenant
from apps.accounts.tenant_emission import (
    apply_emission_flags,
    default_emission_settings,
    emission_flags_from_settings,
    nfe_enabled_for_tenant,
    nfse_enabled_for_tenant,
)


@pytest.mark.django_db
def test_nfse_default_true_for_legacy_empty_settings():
    tenant = Tenant.objects.create(
        slug="legacy-nfse",
        legal_name="Legacy",
        document="00000000000191",
        settings={},
    )
    assert nfse_enabled_for_tenant(tenant) is True
    assert nfe_enabled_for_tenant(tenant) is False


@pytest.mark.django_db
def test_emission_flags_roundtrip(settings):
    settings.NFE_ENABLED = True
    tenant = Tenant.objects.create(
        slug="both-types",
        legal_name="Both",
        document="00000000000192",
        settings=apply_emission_flags({}, nfse=True, nfe=True),
    )
    assert nfse_enabled_for_tenant(tenant) is True
    assert nfe_enabled_for_tenant(tenant) is True
    nfse, nfe, nfce = emission_flags_from_settings(tenant.settings)
    assert nfse is True and nfe is True and nfce is False


@pytest.mark.django_db
def test_tenant_admin_form_requires_at_least_one_emission_type():
    form = TenantAdminForm(
        data={
            "slug": "x",
            "legal_name": "X",
            "document": "00000000000193",
            "status": "active",
            "focus_layout": "nfsen",
            "settings": "{}",
            "emit_nfse": False,
            "emit_nfe": False,
            "emit_nfce": False,
        }
    )
    assert not form.is_valid()
    assert "pelo menos um tipo" in str(form.errors).lower()


@pytest.mark.django_db
def test_tenant_admin_form_accepts_both():
    form = TenantAdminForm(
        data={
            "slug": "both",
            "legal_name": "Both",
            "document": "00000000000194",
            "status": "active",
            "focus_layout": "nfsen",
            "settings": "{}",
            "emit_nfse": True,
            "emit_nfe": True,
            "emit_nfce": False,
        }
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_tenant_admin_form_accepts_nfce_only():
    form = TenantAdminForm(
        data={
            "slug": "nfce-only",
            "legal_name": "NFCe",
            "document": "00000000000196",
            "status": "active",
            "focus_layout": "nfsen",
            "settings": "{}",
            "emit_nfse": False,
            "emit_nfe": False,
            "emit_nfce": True,
        }
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_tenant_admin_form_persists_settings():
    form = TenantAdminForm(
        data={
            "slug": "persist",
            "legal_name": "Persist",
            "document": "00000000000195",
            "status": "active",
            "focus_layout": "nfsen",
            "settings": '{"payment_provider": "inter"}',
            "emit_nfse": True,
            "emit_nfe": False,
            "emit_nfce": False,
        }
    )
    assert form.is_valid(), form.errors
    tenant = form.save()
    assert tenant.settings["nfse_enabled"] is True
    assert tenant.settings["nfe_enabled"] is False
    assert tenant.settings["payment_provider"] == "inter"


def test_default_emission_settings_onboarding():
    cfg = default_emission_settings()
    assert cfg["nfse_enabled"] is True
    assert cfg["nfe_enabled"] is False
