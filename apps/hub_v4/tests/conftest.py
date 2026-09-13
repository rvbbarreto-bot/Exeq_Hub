"""Fixtures Hub — NF-e de entrada."""

from __future__ import annotations

import pytest

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once


@pytest.fixture
def hub_entrada_ctx(db, settings):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-entrada-hub",
        legal_name="NFe Entrada Hub",
        document="11222333000181",
        settings={"nfe_entrada_enabled": True},
    )
    user = User.objects.create_user(
        email="nfe.entrada@exeq.local", password="Secret123!", name="Entrada Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )
    sync_distribuicao_once(tenant=tenant, provider=provider, stub_mode="138")
    doc = NfeEntradaDocument.objects.filter(tenant=tenant).first()
    return {"tenant": tenant, "user": user, "provider": provider, "doc": doc}


@pytest.fixture
def entrada_settings(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )
