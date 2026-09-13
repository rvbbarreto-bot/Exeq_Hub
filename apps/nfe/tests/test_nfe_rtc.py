"""NF-e RTC shadow — validação e snapshot forensic."""

from __future__ import annotations

from datetime import date

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.services import (
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
    validate_invoice,
)


@pytest.fixture
def nfe_rtc_settings(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_RTC_MODE = "shadow"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_enabled": True}
    tenant_a.save(update_fields=["settings"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
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
def test_nfe_validation_rtc_shadow(nfe_rtc_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="RTC-NFE",
        description="Item RTC",
        ncm="21069090",
        unit_price_cents=10_000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="nfe-rtc-val",
        issue_date=date(2026, 9, 4),
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    result = validate_invoice(inv)
    assert result["ok"] is True
    assert result["totals"]["rtc"]["v_cbs_cents"] == 90
    assert result["items_taxes"][0]["taxes"]["rtc"]["mode"] == "shadow"


@pytest.mark.django_db
def test_nfe_emit_includes_forensic(nfe_rtc_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="RTC-NFE2",
        description="Item RTC",
        ncm="21069090",
        unit_price_cents=10_000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="nfe-rtc-emit",
        issue_date=date(2026, 9, 4),
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    inv = emit_invoice(inv)
    forensic = (inv.fiscal_snapshot or {}).get("forensic") or {}
    assert forensic.get("schema") == "exeq.fiscal.forensic.v1"
    assert forensic.get("rtc", {}).get("mode") == "shadow"
