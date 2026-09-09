"""Testes ADR-GOODS-VALIDATE-V1."""

from __future__ import annotations

import pytest

from apps.fiscal.goods_validate import (
    effective_cross_validate_mode,
    normalize_gtin,
    resolve_c_ean,
    validate_fiscal_profile_product,
)
from apps.nfe.cross_validate import cross_validate_mode, validate_product_fields
from integrations.sefaz_nfe.prod_fields import prod_c_ean


def test_resolve_c_ean_sem_gtin():
    assert resolve_c_ean("") == "SEM GTIN"
    assert resolve_c_ean(None) == "SEM GTIN"
    assert prod_c_ean({}) == "SEM GTIN"


def test_resolve_c_ean_valid():
    assert resolve_c_ean("7891234567890") == "7891234567890"


def test_normalize_gtin_strips_sem_gtin():
    assert normalize_gtin("SEM GTIN") == ""
    assert normalize_gtin(" 7891234567890 ") == "7891234567890"


def test_simple_retail_blocks_st_cfop():
    errors = validate_fiscal_profile_product(
        fiscal_profile="simple_retail",
        cfop_internal="5405",
        cfop_interstate="6102",
        csosn="102",
    )
    assert any(e["rule"] == "RULE-PROFILE-ST" for e in errors)


def test_simple_retail_blocks_csosn_500():
    errors = validate_fiscal_profile_product(
        fiscal_profile="simple_retail",
        cfop_internal="5102",
        cfop_interstate="6102",
        csosn="500",
    )
    assert any("CSOSN 500" in e["message"] for e in errors)


def test_effective_mode_catalog_is_warn(settings):
    settings.GOODS_CROSS_VALIDATE = "block"
    assert effective_cross_validate_mode(context="catalog") == "warn"


def test_effective_mode_emit_http_is_block(settings):
    settings.GOODS_CROSS_VALIDATE = "warn"
    assert effective_cross_validate_mode(context="emit", http_emit=True) == "block"


@pytest.mark.django_db
def test_validate_product_blocks_st_for_simple_retail_tenant(settings):
    from apps.accounts.models import Tenant

    tenant = Tenant.objects.create(
        slug="goods-val",
        legal_name="Goods Val",
        document="60746948000112",
        settings={"fiscal_profile": "simple_retail"},
    )
    errors = validate_product_fields(
        ncm="21069090",
        unit="UN",
        cfop_internal="5405",
        cfop_interstate="6102",
        csosn="102",
        tenant=tenant,
        context="catalog",
        check_catalog=False,
    )
    assert any("simple_retail" in e for e in errors)


def test_cross_validate_mode_uses_goods_flag(settings):
    settings.GOODS_CROSS_VALIDATE = "block"
    assert cross_validate_mode(context="draft") == "block"
