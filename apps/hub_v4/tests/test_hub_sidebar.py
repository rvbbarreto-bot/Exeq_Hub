"""Navegação lateral Hub V4 — config PO + acordeão."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.hub_v4.sidebar import build_sidebar_navigation


@pytest.fixture
def hub_sidebar_ctx(db, settings):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nav-qa",
        legal_name="Nav QA",
        document="60746948000112",
        settings={"nfe_enabled": True, "nfce_enabled": True, "nfse_enabled": False},
    )
    user = User.objects.create_user(
        email="nav@exeq.local", password="Secret123!", name="Nav"
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
def test_sidebar_renders_accordion_groups(client, hub_sidebar_ctx, settings):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    tenant, user = hub_sidebar_ctx
    _login(client, tenant, user)
    r = client.get(reverse("hub-v4-dashboard"))
    body = r.content.decode()
    assert "nav-accordion" in body
    assert "Exeq Fiscal" in body
    assert "Cadastro Empresa" in body
    assert "Financeiro" in body
    assert "Emissão NF-e" in body
    assert "Emissão NFC-e avulsa" in body
    assert "Emissão NFS-e" not in body  # nfse flag off neste fixture
    assert reverse("hub-v4-nfe-list") in body


@pytest.mark.django_db
def test_sidebar_hides_nfe_when_flag_off(client, hub_sidebar_ctx, settings):
    settings.NFE_ENABLED = False
    tenant, user = hub_sidebar_ctx
    _login(client, tenant, user)
    body = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert "Emissão NF-e" not in body


@pytest.mark.django_db
def test_build_sidebar_nfe_list_not_active_on_products(settings):
    settings.NFE_ENABLED = True
    rf = RequestFactory()
    request = rf.get("/hub/nfe/produtos/")
    flags = {"nfe_enabled_nav": True, "nfce_enabled_nav": False, "nfse_enabled_nav": False}
    groups = build_sidebar_navigation(request=request, flags=flags)
    fiscal = next(g for g in groups if g["title"] == "Exeq Fiscal")
    cadastro = next(g for g in groups if g["title"] == "Cadastro Empresa")
    assert cadastro["expanded"] is True
    assert fiscal["expanded"] is False
    nfe = next(i for i in fiscal["items"] if i["nav"] == "nfe")
    produtos = next(i for i in cadastro["items"] if i["nav"] == "nfe_products")
    assert produtos["active"] is True
    assert nfe["active"] is False


@pytest.mark.django_db
def test_build_sidebar_expands_cadastro_for_nfe_products(settings):
    settings.NFE_ENABLED = True
    rf = RequestFactory()
    request = rf.get("/hub/nfe/produtos/")
    flags = {"nfe_enabled_nav": True, "nfce_enabled_nav": False, "nfse_enabled_nav": False}
    groups = build_sidebar_navigation(request=request, flags=flags)
    cadastro = next(g for g in groups if g["title"] == "Cadastro Empresa")
    assert cadastro["expanded"] is True
    produtos = next(i for i in cadastro["items"] if i["nav"] == "nfe_products")
    assert produtos["active"] is True
    fiscal = next(g for g in groups if g["title"] == "Exeq Fiscal")
    assert all(i["nav"] != "nfe_products" for i in fiscal["items"])


@pytest.mark.django_db
def test_build_sidebar_expands_active_group(settings):
    settings.NFE_ENABLED = True
    rf = RequestFactory()
    request = rf.get("/hub/nfe/")
    flags = {"nfe_enabled_nav": True, "nfce_enabled_nav": False, "nfse_enabled_nav": False}
    groups = build_sidebar_navigation(request=request, flags=flags)
    fiscal = next(g for g in groups if g["title"] == "Exeq Fiscal")
    assert fiscal["expanded"] is True
    nfe = next(i for i in fiscal["items"] if i["nav"] == "nfe")
    assert nfe["active"] is True
