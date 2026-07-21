"""Agenda de vencimentos para cobrança parcelada / recorrente."""

from __future__ import annotations

import calendar
from datetime import date


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def split_amount_cents(total_cents: int, parts: int) -> list[int]:
    if parts < 1:
        raise ValueError("parts deve ser >= 1")
    base, rem = divmod(total_cents, parts)
    amounts = [base] * parts
    for i in range(rem):
        amounts[i] += 1
    return amounts


def build_due_dates(*, first_due: date, count: int) -> list[date]:
    return [add_months(first_due, i) for i in range(count)]


def count_monthly_occurrences(*, first_due: date, end_date: date) -> int:
    if end_date < first_due:
        raise ValueError("recurrence_end_date anterior ao vencimento inicial")
    count = 0
    current = first_due
    # Limite operacional alinhado a carnês típicos
    while current <= end_date and count < 60:
        count += 1
        current = add_months(first_due, count)
    return max(count, 1)


def seu_numero_for_installment(base: str, number: int, total: int) -> str:
    """Gera seuNumero ≤ 15 chars: BASE-NN."""
    suffix = f"-{number:02d}" if total > 9 else f"-{number}"
    room = 15 - len(suffix)
    stem = (base or "COB")[:room]
    return f"{stem}{suffix}"
