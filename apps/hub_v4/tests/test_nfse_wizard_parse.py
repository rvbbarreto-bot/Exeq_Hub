"""Parsing e POST do wizard NFS-e."""

from __future__ import annotations

import pytest

from apps.hub_v4.forms import parse_brl_amount_cents


def test_parse_brl_amount_cents_formats():
    assert parse_brl_amount_cents("20,00") == 2000
    assert parse_brl_amount_cents("1.500,00") == 150000
    assert parse_brl_amount_cents("R$ 20,00") == 2000
    assert parse_brl_amount_cents("  199,90 ") == 19990


def test_parse_brl_amount_cents_empty():
    with pytest.raises(ValueError, match="Informe o valor"):
        parse_brl_amount_cents("")


def test_parse_brl_amount_cents_invalid():
    with pytest.raises(ValueError, match="Valor inválido"):
        parse_brl_amount_cents("abc")
