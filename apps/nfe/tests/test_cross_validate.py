"""Validação cruzada produto NF-e."""

from __future__ import annotations

import pytest

from apps.nfe.cross_validate import validate_product_fields


def test_cfop_prefix_rules():
    errors = validate_product_fields(
        ncm="21069090",
        unit="UN",
        cfop_internal="6102",
        cfop_interstate="5102",
        csosn="102",
        check_catalog=False,
    )
    assert any("interno" in e for e in errors)
    assert any("interestadual" in e for e in errors)


def test_sn_csosn_vs_cst():
    errors = validate_product_fields(
        ncm="21069090",
        unit="UN",
        cfop_internal="5102",
        cfop_interstate="6102",
        csosn="102",
        icms_cst="00",
        check_catalog=False,
    )
    assert any("CST ICMS" in e for e in errors)


@pytest.mark.django_db
def test_strict_catalog(settings):
    settings.NFE_CATALOG_STRICT = True
    errors = validate_product_fields(
        ncm="99999999",
        unit="UN",
        cfop_internal="5102",
        cfop_interstate="6102",
        csosn="102",
    )
    assert any("NCM" in e for e in errors)
