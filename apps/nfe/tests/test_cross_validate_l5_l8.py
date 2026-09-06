"""CrossValidator L1–L8 integração."""

from __future__ import annotations

from datetime import date

import pytest

from apps.fiscal.rtc_classification import seed_minimal_rtc_pack
from apps.nfe.cross_validate import (
    cross_validate_invoice_item,
    cross_validate_mode,
    cross_validate_product,
)


def test_cross_validate_mode_off(settings):
    settings.NFE_CROSS_VALIDATE = "off"
    assert cross_validate_mode() == "off"
    result = cross_validate_product(
        ncm="21069090",
        unit="UN",
        cfop_internal="5405",
        cfop_interstate="6405",
        csosn="102",
    )
    assert result["ok"] is True
    assert result["errors"] == []


def test_cross_validate_mode_invalid_defaults_warn(settings):
    settings.NFE_CROSS_VALIDATE = "invalid"
    assert cross_validate_mode() == "warn"


def test_cross_validate_mode_default_warn(settings):
    assert cross_validate_mode() == "warn"


def test_invoice_item_off_mode(settings):
    settings.NFE_CROSS_VALIDATE = "off"
    result = cross_validate_invoice_item(
        line_number=2,
        ncm="21069090",
        cfop="5405",
        pis_cst="07",
        cofins_cst="07",
        issue_date=date(2026, 1, 1),
        crt="simples_nacional",
    )
    assert result["ok"] is True


def test_product_catalog_strict_errors(settings):
    settings.NFE_CROSS_VALIDATE = "block"
    result = cross_validate_product(
        ncm="21069090",
        unit="UN",
        cfop_internal="5405",
        cfop_interstate="6405",
        csosn="102",
        cest="",
    )
    assert result["ok"] is False
    assert any("CEST" in e["message"] for e in result["errors"])


def test_product_l5_warn_mode(settings):
    settings.NFE_CROSS_VALIDATE = "warn"
    result = cross_validate_product(
        ncm="22021000",
        unit="UN",
        cfop_internal="5101",
        cfop_interstate="6102",
        csosn="102",
    )
    assert result["ok"] is True
    assert any("Capítulo 22" in w["message"] for w in result["warnings"])


def test_invoice_item_st_hard_in_warn(settings):
    settings.NFE_CROSS_VALIDATE = "warn"
    result = cross_validate_invoice_item(
        line_number=1,
        ncm="21069090",
        cfop="5405",
        pis_cst="07",
        cofins_cst="07",
        cest="",
        issue_date=date(2026, 1, 1),
        crt="simples_nacional",
    )
    assert result["ok"] is False


@pytest.mark.django_db
def test_product_ipi_fields_persist(settings, tenant_a):
    settings.NFE_ENABLED = True
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_enabled": True}
    tenant_a.save(update_fields=["settings"])
    from apps.nfe.services import create_product

    p = create_product(
        tenant=tenant_a,
        code="IPI-1",
        description="Com IPI",
        ncm="21069090",
        ipi_rate_bp=500,
        ipi_cst="50",
        ip_enq="999",
        csosn="102",
    )
    assert p.ipi_rate_bp == 500
    assert p.ip_enq == "999"


@pytest.mark.django_db
def test_validate_invoice_cross_st_integration(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFE_CROSS_VALIDATE = "block"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_enabled": True}
    tenant_a.save(update_fields=["settings"])

    from apps.master_data.models import Customer, Provider, TaxRegime
    from apps.nfe.services import create_draft, create_product, replace_items, validate_invoice

    provider = Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Emit",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )
    customer = Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av B",
            "numero": "2",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
    )
    product = create_product(
        tenant=tenant_a,
        code="ST-BAD",
        description="ST sem CEST na linha",
        ncm="21069090",
        cfop_internal="5102",
        cfop_interstate="6102",
        csosn="102",
        unit_price_cents=1000,
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider,
        customer=customer,
        idempotency_key="st-xval",
    )
    replace_items(
        inv,
        items=[{"product_id": str(product.id), "quantity": "1", "cfop": "5405"}],
    )
    inv.refresh_from_db()
    result = validate_invoice(inv)
    assert result["ok"] is False
    assert any("CEST" in str(e.get("message", "")) for e in result["field_errors"])


@pytest.mark.django_db
def test_l8_emit_with_seed(settings):
    settings.NFE_RTC_MODE = "emit"
    seed_minimal_rtc_pack()
    result = cross_validate_product(
        ncm="21069090",
        unit="UN",
        cfop_internal="5102",
        cfop_interstate="6102",
        csosn="102",
        crt="3",
        issue_date=date(2026, 9, 1),
    )
    assert result["ok"] is True
