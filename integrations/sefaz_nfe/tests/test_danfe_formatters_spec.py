"""Formatadores DANFE — spec CONSTRUFORTI."""

from __future__ import annotations

from integrations.sefaz_nfe.danfe.formatters import (
    format_approx_trib_percent,
    format_document,
    format_nf_number,
    format_phone_br,
    is_valid_cnpj,
)


def test_format_approx_trib_percent_construforti():
    # R$ 100,44 sobre total R$ 620,00 → 16,2000%
    assert format_approx_trib_percent("100.44", "620.00") == "(16,2000%)"


def test_format_approx_trib_percent_fixture_rich():
    # fixture: vTotTrib 1.50 / vNF 10.00 → 15%
    assert format_approx_trib_percent("1.50", "10.00") == "(15,0000%)"


def test_format_approx_trib_percent_zero_total():
    assert format_approx_trib_percent("1.50", "0.00") == ""


def test_format_document_masks_valid_cnpj():
    assert format_document("61536366000174") == "61.536.366/0001-74"


def test_format_document_rejects_invalid_cnpj_mask():
    assert format_document("12345678000199") == "12345678000199"


def test_is_valid_cnpj_fixture_emitente():
    assert is_valid_cnpj("37229907000137")
