"""Formatação monetária BRL para Admin/UI (armazenamento continua em centavos/Decimal)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def reais_to_cents(value: Decimal | int | float | str) -> int:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValueError("Valor deve ser maior que zero")
    return int(amount * 100)


def cents_to_reais(cents: int | None) -> Decimal:
    if cents is None:
        return Decimal("0.00")
    return (Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01"))


def format_brl(value: Decimal | int | float | str | None) -> str:
    """Formata valor em reais: R$ 1.234,56"""
    if value is None or value == "":
        return "—"
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    formatted = f"{amount:,.2f}"  # 1,234.56
    int_part, frac = formatted.split(".")
    int_part = int_part.replace(",", ".")
    return f"{sign}R$ {int_part},{frac}"


def format_brl_from_cents(cents: int | None) -> str:
    if cents is None:
        return "—"
    return format_brl(cents_to_reais(cents))
