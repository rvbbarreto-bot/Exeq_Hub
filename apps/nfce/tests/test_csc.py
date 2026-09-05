"""CSC NFC-e — resolução tenant DB vs env."""

from __future__ import annotations

import pytest

from apps.master_data.models import Provider, TaxRegime
from apps.nfce.csc import normalize_csc_id, resolve_csc
from apps.nfce.models import TenantCscToken


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="CSC Lab",
        tax_regime=TaxRegime.SIMPLES,
        address={"uf": "SP", "codigo_ibge": "3504107", "logradouro": "Rua A"},
        is_active=True,
    )


def test_normalize_csc_id_strips_zeros():
    assert normalize_csc_id("00001") == "1"
    assert normalize_csc_id("") == "1"


@pytest.mark.django_db
def test_resolve_csc_from_db(settings, tenant_a, provider_sp):
    settings.NFCE_HTTP_MODE = "http"
    settings.NFCE_CSC_TOKEN = "ENVTOKEN"
    TenantCscToken.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        tp_amb="2",
        csc_id="0003",
        csc_token="DBTOKEN123",
        is_active=True,
    )
    cid, tok = resolve_csc(tenant=tenant_a, provider=provider_sp, tp_amb="2")
    assert cid == "3"
    assert tok == "DBTOKEN123"


@pytest.mark.django_db
def test_resolve_csc_env_fallback_http(settings, tenant_a, provider_sp):
    settings.NFCE_HTTP_MODE = "http"
    settings.NFCE_CSC_ID = "2"
    settings.NFCE_CSC_TOKEN = "ENVHOMOLOG"
    cid, tok = resolve_csc(tenant=tenant_a, provider=provider_sp, tp_amb="2")
    assert cid == "2"
    assert tok == "ENVHOMOLOG"


@pytest.mark.django_db
def test_resolve_csc_stub_homolog_default(settings, tenant_a, provider_sp):
    settings.NFCE_HTTP_MODE = "stub"
    settings.NFCE_CSC_TOKEN = ""
    cid, tok = resolve_csc(tenant=tenant_a, provider=provider_sp, tp_amb="2")
    assert cid == "1"
    assert tok == "HOMOLOGCSC"
