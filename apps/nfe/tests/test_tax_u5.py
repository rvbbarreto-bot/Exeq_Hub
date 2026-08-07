"""U5 — interestadual / CFOP / RTC hooks / CCe scaffold."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_draft, create_product, replace_items, validate_invoice
from apps.nfe.tax import (
    TAX_ENGINE_VERSION,
    calculate_item_taxes,
    default_icms_interestadual_rate_bp,
    is_interstate,
    suggest_cfop,
    validate_cfop_against_ufs,
)
from integrations.sefaz_nfe.evento_cce import NfeCceBuildError, build_cce_env_evento_xml


def test_suggest_cfop_internal_vs_inter():
    assert suggest_cfop(emit_uf="SP", dest_uf="SP") == "5102"
    assert suggest_cfop(emit_uf="SP", dest_uf="MG") == "6102"


def test_cfop_validation_rf05():
    assert validate_cfop_against_ufs(cfop="5102", emit_uf="SP", dest_uf="SP") is None
    assert validate_cfop_against_ufs(cfop="6102", emit_uf="SP", dest_uf="MG") is None
    assert "interestadual" in (validate_cfop_against_ufs(cfop="5102", emit_uf="SP", dest_uf="MG") or "")
    assert "interna" in (validate_cfop_against_ufs(cfop="6102", emit_uf="SP", dest_uf="SP") or "")


def test_interestadual_rates():
    assert default_icms_interestadual_rate_bp(emit_uf="SP", dest_uf="SP") == 0
    assert default_icms_interestadual_rate_bp(emit_uf="SP", dest_uf="MG") == 1200
    assert default_icms_interestadual_rate_bp(emit_uf="SP", dest_uf="BA") == 700
    assert is_interstate(emit_uf="SP", dest_uf="RJ") is True


def test_normal_cst00_interestadual_uses_default_rate():
    tax = calculate_item_taxes(
        tax_regime=TaxRegime.PRESUMIDO,
        item_total_cents=10_000,
        icms_rate_bp=0,
        csosn="",
        icms_cst="00",
        origin="0",
        pis_cst="07",
        pis_rate_bp=0,
        cofins_cst="07",
        cofins_rate_bp=0,
        emit_uf="SP",
        dest_uf="MG",
    )
    assert tax["icms"]["interstate"] is True
    assert tax["icms"]["rate_bp"] == 1200
    assert tax["icms"]["value_cents"] == 1200  # 12% of 10000
    assert tax["rtc"]["ibs"] is None
    assert "u5" in TAX_ENGINE_VERSION


def test_cce_build_and_validation():
    raw = build_cce_env_evento_xml(
        access_key="35260837229907000137550010000000011000000010",
        cnpj="37229907000137",
        x_correcao="Correcao de descricao do item 1 sem impacto em base ou aliquota.",
        tp_amb="2",
        dh_evento=datetime(2026, 8, 6, 12, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )
    text = raw.decode("utf-8")
    assert "110110" in text
    assert "Carta de Correcao" in text or "Carta de Correcao" in text.replace("ç", "c")
    assert "xCorrecao" in text
    with pytest.raises(NfeCceBuildError):
        build_cce_env_evento_xml(
            access_key="35260837229907000137550010000000011000000010",
            cnpj="37229907000137",
            x_correcao="curto",
        )


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
        tax_regime=TaxRegime.PRESUMIDO,
        state_registration="123456789112",
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


@pytest.fixture
def customer_mg(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente MG",
        address={
            "logradouro": "Av BH",
            "numero": "100",
            "bairro": "Centro",
            "municipio": "Belo Horizonte",
            "uf": "MG",
            "cep": "30130000",
            "codigo_ibge": "3106200",
        },
    )


@pytest.mark.django_db
def test_replace_items_auto_cfop_inter(nfe_settings, tenant_a, provider_sp, customer_mg):
    product = create_product(
        tenant=tenant_a,
        code="INT1",
        description="Item inter",
        ncm="21069090",
        unit_price_cents=5000,
        icms_cst="00",
        csosn="",
    )
    # create_product may force csosn - check model
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_mg,
        idempotency_key="u5-inter-1",
        issue_date=date(2026, 8, 6),
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    item = inv.items.get()
    assert item.cfop == "6102"
    val = validate_invoice(inv)
    assert val["totals"]["operation"]["interstate"] is True
    assert val["totals"]["operation"]["id_dest"] == "2"
    assert not any(e["field"].endswith(".cfop") for e in val["field_errors"])


@pytest.mark.django_db
def test_validate_rejects_internal_cfop_on_inter(
    nfe_settings, tenant_a, provider_sp, customer_mg
):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_mg,
        idempotency_key="u5-inter-bad-cfop",
    )
    replace_items(
        inv,
        items=[
            {
                "code": "X",
                "description": "Item",
                "ncm": "21069090",
                "cfop": "5102",
                "quantity": "1",
                "unit_price_cents": 1000,
                "csosn": "102",
            }
        ],
    )
    # force NORMAL path not needed for CFOP check
    val = validate_invoice(inv)
    assert val["ok"] is False
    assert any("interestadual" in e["message"] for e in val["field_errors"])
