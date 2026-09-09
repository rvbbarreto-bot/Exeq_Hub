"""Fixtures compartilhadas — testes NF-e de entrada."""

from __future__ import annotations

import pytest

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once


@pytest.fixture
def entrada_settings(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    settings.NFE_ENTRADA_BLOCK_656_SECONDS = 3600
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


@pytest.fixture
def provider_beta(tenant_b):
    return Provider.objects.create(
        tenant=tenant_b,
        document="11222333000181",
        legal_name="BETA LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="99999",
        address={"uf": "SP", "municipio": "São Paulo", "codigo_ibge": "3550308"},
    )


@pytest.fixture
def entrada_doc(entrada_settings, tenant_a, provider_sp):
    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    return NfeEntradaDocument.objects.filter(tenant=tenant_a).order_by("nsu").first()


STUB_KEY = "35260137229907000137550010000000000000000001"
