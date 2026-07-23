"""Regras monetárias de cobrança (Inter Cobrança v3)."""

from __future__ import annotations

# Valor mínimo Inter: R$ 2,50
CHARGE_MIN_AMOUNT_CENTS = 250
CHARGE_MIN_AMOUNT_BRL = "R$ 2,50"


def validate_charge_amount_cents(amount_cents: int) -> None:
    """Raise ValueError se abaixo do mínimo Inter."""
    if int(amount_cents) < CHARGE_MIN_AMOUNT_CENTS:
        raise ValueError(
            f"Valor mínimo da cobrança é {CHARGE_MIN_AMOUNT_BRL} "
            f"({CHARGE_MIN_AMOUNT_CENTS} centavos)."
        )
