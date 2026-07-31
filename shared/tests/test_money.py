from decimal import Decimal

import pytest

from shared.money import (
    cents_to_reais,
    format_brl,
    format_brl_from_cents,
    reais_to_cents,
)


def test_format_brl_from_cents():
    assert format_brl_from_cents(1000) == "R$ 10,00"
    assert format_brl_from_cents(15050) == "R$ 150,50"
    assert format_brl_from_cents(1_234_567) == "R$ 12.345,67"
    assert format_brl_from_cents(None) == "—"


def test_format_brl_decimal():
    assert format_brl(Decimal("0.00")) == "R$ 0,00"
    assert format_brl(Decimal("99.9")) == "R$ 99,90"


def test_reais_to_cents_roundtrip():
    assert reais_to_cents(Decimal("10.00")) == 1000
    assert reais_to_cents("150,50".replace(",", ".")) == 15050
    assert cents_to_reais(1000) == Decimal("10.00")
    with pytest.raises(ValueError):
        reais_to_cents(Decimal("0"))
