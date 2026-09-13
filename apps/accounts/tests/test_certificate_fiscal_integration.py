"""
Integração certificado A1 × emissões fiscais (NF-e, NFC-e, NFS-e, DAS).

Cobre key_usage, load_primary_pfx_material por purpose e backfill legado.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.accounts.certificates import (
    DEFAULT_KEY_USAGE,
    assert_certificate_usable,
    backfill_legacy_key_usage,
    certificate_purpose_ok,
    default_key_usage_for_tenant,
    load_primary_pfx_material,
    upload_a1_certificate,
)
from apps.accounts.exceptions import CertificateNotUsableError
from apps.accounts.models import DigitalCertificate, Tenant
from apps.accounts.tests.test_secrets_certificates import _make_pfx
from apps.master_data.models import Provider, TaxRegime
from apps.nfe.gate import build_gate_payload
from apps.nfce.gate import build_gate_payload as build_nfce_gate_payload
from integrations.sefaz_nfe.port import HttpNfeProvider


@pytest.fixture
def nfe_tenant(db):
    return Tenant.objects.create(
        slug="cert-nfe",
        legal_name="Cert NF-e",
        document="11222333000181",
        settings={"nfe_enabled": True, "nfse_enabled": False},
    )


@pytest.fixture
def nfce_tenant(db):
    return Tenant.objects.create(
        slug="cert-nfce",
        legal_name="Cert NFC-e",
        document="22333444000192",
        settings={"nfce_enabled": True, "nfse_enabled": False, "nfe_enabled": False},
    )


@pytest.fixture
def nfse_only_tenant(db):
    return Tenant.objects.create(
        slug="cert-nfse",
        legal_name="Cert NFS-e",
        document="33444555000103",
        settings={"nfse_enabled": True, "nfe_enabled": False, "nfce_enabled": False},
    )


def _upload(
    *,
    tenant,
    cnpj: str = "00000000000191",
    key_usage=None,
    tmp_path,
    settings,
):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    return upload_a1_certificate(
        tenant=tenant,
        label="A1",
        cnpj=cnpj,
        pfx_bytes=_make_pfx(days=90),
        password="secret",
        key_usage=key_usage,
    )


@pytest.mark.django_db
def test_default_key_usage_for_nfe_tenant(nfe_tenant):
    assert "nfe" in default_key_usage_for_tenant(nfe_tenant)
    assert "das" in default_key_usage_for_tenant(nfe_tenant)


@pytest.mark.django_db
def test_default_key_usage_nfse_only_excludes_nfe(nfse_only_tenant):
    usages = default_key_usage_for_tenant(nfse_only_tenant)
    assert usages == ["das", "nfse"]


@pytest.mark.django_db
def test_upload_default_includes_nfe(nfe_tenant, tmp_path, settings):
    cert = _upload(tenant=nfe_tenant, tmp_path=tmp_path, settings=settings)
    assert cert.key_usage == ["das", "nfe"]


@pytest.mark.django_db
def test_load_pfx_nfe_after_default_upload(nfe_tenant, tmp_path, settings):
    cnpj = "61536366000174"
    _upload(tenant=nfe_tenant, cnpj=cnpj, tmp_path=tmp_path, settings=settings)
    pfx, pwd = load_primary_pfx_material(tenant=nfe_tenant, cnpj=cnpj, purpose="nfe")
    assert isinstance(pfx, bytes) and len(pfx) > 0
    assert pwd == "secret"


@pytest.mark.django_db
def test_legacy_key_usage_blocks_nfe_purpose(tenant_a, tmp_path, settings):
    cnpj = "00000000000191"
    _upload(
        tenant=tenant_a,
        cnpj=cnpj,
        key_usage=["das", "nfse"],
        tmp_path=tmp_path,
        settings=settings,
    )
    with pytest.raises(CertificateNotUsableError, match="nfe"):
        load_primary_pfx_material(tenant=tenant_a, cnpj=cnpj, purpose="nfe")
    ok, msg = certificate_purpose_ok(tenant=tenant_a, cnpj=cnpj, purpose="nfe")
    assert ok is False
    assert "nfe" in msg


@pytest.mark.django_db
def test_backfill_legacy_key_usage_adds_nfe(tenant_a, tmp_path, settings):
    cert = _upload(
        tenant=tenant_a,
        key_usage=["das", "nfse"],
        tmp_path=tmp_path,
        settings=settings,
    )
    assert backfill_legacy_key_usage() == 1
    cert.refresh_from_db()
    assert cert.key_usage == ["das", "nfse", "nfe"]
    load_primary_pfx_material(tenant=tenant_a, cnpj=cert.cnpj, purpose="nfe")


@pytest.mark.django_db
def test_custom_key_usage_respected(tenant_a, tmp_path, settings):
    cert = _upload(
        tenant=tenant_a,
        key_usage=["das"],
        tmp_path=tmp_path,
        settings=settings,
    )
    assert_certificate_usable(tenant=tenant_a, cnpj=cert.cnpj, purpose="das")
    with pytest.raises(CertificateNotUsableError):
        assert_certificate_usable(tenant=tenant_a, cnpj=cert.cnpj, purpose="nfse")


@pytest.mark.django_db
def test_nfe_gate_http_blocks_legacy_cert_usage(nfe_tenant, tmp_path, settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "http"
    provider = Provider.objects.create(
        tenant=nfe_tenant,
        document="61536366000174",
        legal_name="Emit",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="123456789112",
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )
    _upload(
        tenant=nfe_tenant,
        cnpj=provider.document,
        key_usage=["das", "nfse"],
        tmp_path=tmp_path,
        settings=settings,
    )
    payload = build_gate_payload(tenant=nfe_tenant, provider_id=str(provider.id))
    usage = next(c for c in payload["checks"] if c["id"] == "cert_nfe_usage")
    assert usage["ok"] is False
    assert payload["can_create"] is False


@pytest.mark.django_db
def test_nfe_gate_http_passes_with_nfe_usage(nfe_tenant, tmp_path, settings):
    from apps.nfe.gate import upsert_number_series

    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "http"
    provider = Provider.objects.create(
        tenant=nfe_tenant,
        document="61536366000174",
        legal_name="Emit",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="123456789112",
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )
    _upload(tenant=nfe_tenant, cnpj=provider.document, tmp_path=tmp_path, settings=settings)
    upsert_number_series(tenant=nfe_tenant, provider=provider, series=1, tp_amb="1")
    payload = build_gate_payload(tenant=nfe_tenant, provider_id=str(provider.id))
    usage = next(c for c in payload["checks"] if c["id"] == "cert_nfe_usage")
    assert usage["ok"] is True


@pytest.mark.django_db
def test_nfce_gate_http_cert_nfe_usage(nfce_tenant, tmp_path, settings):
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "http"
    provider = Provider.objects.create(
        tenant=nfce_tenant,
        document="37229907000137",
        legal_name="PDV",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="123456789112",
        address={
            "logradouro": "Rua B",
            "numero": "2",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )
    _upload(
        tenant=nfce_tenant,
        cnpj=provider.document,
        key_usage=list(DEFAULT_KEY_USAGE),
        tmp_path=tmp_path,
        settings=settings,
    )
    payload = build_nfce_gate_payload(tenant=nfce_tenant, provider_id=str(provider.id))
    usage = next(c for c in payload["checks"] if c["id"] == "cert_nfe_usage")
    assert usage["ok"] is True


@pytest.mark.django_db
def test_http_nfe_cancel_fails_without_nfe_key_usage(tenant_a, tmp_path, settings):
    cnpj = "61536366000174"
    _upload(
        tenant=tenant_a,
        cnpj=cnpj,
        key_usage=["das", "nfse"],
        tmp_path=tmp_path,
        settings=settings,
    )
    provider = HttpNfeProvider()
    result = provider.cancelar(
        access_key="35260961536366000174550010000000021000159350",
        justificativa="Cancelamento teste integracao certificado digital.",
        context={
            "tenant": tenant_a,
            "cnpj": cnpj,
            "protocol": "135260000000001",
            "tp_amb": "2",
            "uf": "SP",
        },
    )
    assert result.status == "failed"
    assert result.rejection_code == "CERT"
    assert "nfe" in (result.rejection_message or "").lower()


@pytest.mark.django_db
def test_das_nfse_nfe_with_full_default_upload(nfe_tenant, tmp_path, settings):
    cert = _upload(
        tenant=nfe_tenant,
        cnpj="61536366000174",
        key_usage=list(DEFAULT_KEY_USAGE),
        tmp_path=tmp_path,
        settings=settings,
    )
    assert_certificate_usable(tenant=nfe_tenant, cnpj=cert.cnpj, purpose="das")
    assert_certificate_usable(tenant=nfe_tenant, cnpj=cert.cnpj, purpose="nfse")
    assert_certificate_usable(tenant=nfe_tenant, cnpj=cert.cnpj, purpose="nfe")


@pytest.mark.django_db
def test_revoked_cert_blocks_all_purposes(tenant_a, tmp_path, settings):
    cert = _upload(tenant=tenant_a, tmp_path=tmp_path, settings=settings)
    DigitalCertificate.objects.filter(id=cert.id).update(
        status=DigitalCertificate.Status.REVOKED
    )
    for purpose in ("das", "nfse", "nfe"):
        with pytest.raises(CertificateNotUsableError, match="revogado"):
            assert_certificate_usable(tenant=tenant_a, cnpj=cert.cnpj, purpose=purpose)
