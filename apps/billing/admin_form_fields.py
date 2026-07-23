"""Formatação monetária BRL e widgets numéricos para o Admin de Charge."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django import forms


_INT_ONLY = re.compile(r"^\d+$")
_DECIMAL_BR = re.compile(r"^\d+([.,]\d{1,2})?$")


class NumericTextInput(forms.TextInput):
    """Evita type=number (que aceita 'e' em notação científica no browser)."""

    def __init__(self, attrs=None, *, decimal=False):
        base = {
            "inputmode": "decimal" if decimal else "numeric",
            "autocomplete": "off",
            "pattern": r"[0-9]+([.,][0-9]{1,2})?" if decimal else r"[0-9]*",
        }
        if attrs:
            base.update(attrs)
        super().__init__(attrs=base)


def parse_br_decimal(raw) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(" ", "")
    if text == "":
        return None
    if not _DECIMAL_BR.fullmatch(text):
        raise forms.ValidationError(
            "Informe apenas números (ex.: 2 ou 2,50).",
            code="invalid",
        )
    normalized = text.replace(",", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise forms.ValidationError("Número inválido.", code="invalid") from exc


def parse_int_digits(raw) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    if not _INT_ONLY.fullmatch(text):
        raise forms.ValidationError(
            "Informe apenas números inteiros.",
            code="invalid",
        )
    return int(text)


def parse_valor_reais_to_cents(raw: str) -> int:
    from shared.money import reais_to_cents

    text = (raw or "").strip().replace("R$", "").replace("r$", "").strip()
    if not text:
        raise forms.ValidationError("Informe o valor.", code="required")
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", text):
        raise forms.ValidationError(
            "Valor inválido. Use o formato 6,00.",
            code="invalid",
        )
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise forms.ValidationError("Valor inválido. Use o formato 6,00.") from exc
    try:
        return reais_to_cents(value)
    except ValueError as exc:
        raise forms.ValidationError(str(exc)) from exc
