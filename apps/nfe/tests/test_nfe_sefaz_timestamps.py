"""NF-e dhEmi/dhRecbto no emit stub."""

from __future__ import annotations

import re

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    return settings


@pytest.fixture
def nfe_tenant(tenant_a, nfe_settings):
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_enabled": True}
    tenant_a.save(update_fields=["settings"])
    return tenant_a


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua Teste",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av Teste",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_emit_stamps_dh_emi_and_recbto(nfe_settings, nfe_tenant, provider_sp, customer_b2b):
    product = create_product(
        tenant=nfe_tenant,
        code="TS1",
        description="Produto",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=nfe_tenant,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="nfe-ts-1",
    )
    replace_items(
        inv,
        items=[{"product_id": str(product.id), "quantity": "1"}],
    )
    inv.refresh_from_db()
    inv = emit_invoice(inv)

    snap = inv.fiscal_snapshot or {}
    dh_emi = (snap.get("header") or {}).get("dh_emi", "")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", dh_emi)
    assert dh_emi.endswith("-03:00") or dh_emi.endswith("-02:00")
    assert "T12:00:00" not in dh_emi

    dh_recbto = (snap.get("sefaz") or {}).get("dh_recbto", "")
    assert dh_recbto

    xml = build_nfe_xml(snapshot=snap)
    assert dh_emi in xml.decode("utf-8")


@pytest.mark.django_db
def test_snapshot_includes_catalog_versions(nfe_settings, nfe_tenant, provider_sp, customer_b2b):
    product = create_product(
        tenant=nfe_tenant,
        code="TS2",
        description="Produto",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=nfe_tenant,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="nfe-ts-2",
    )
    replace_items(
        inv,
        items=[{"product_id": str(product.id), "quantity": "1"}],
    )
    inv.refresh_from_db()
    inv = emit_invoice(inv)
    versions = (inv.fiscal_snapshot or {}).get("catalog_versions") or {}
    assert versions.get("catalog_version")
