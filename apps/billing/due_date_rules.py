"""Regras de vencimento para emissão de boleto (Admin/API)."""

from __future__ import annotations

from datetime import date, time, timedelta

from django.utils import timezone

# Após este horário (fuso local Django), o vencimento mínimo passa a ser o dia seguinte.
BOLETO_DUE_CUTOFF = time(16, 0)


def min_due_date(*, now=None) -> date:
    current = timezone.localtime(now) if now is not None else timezone.localtime()
    today = current.date()
    if (current.hour, current.minute, current.second) >= (
        BOLETO_DUE_CUTOFF.hour,
        BOLETO_DUE_CUTOFF.minute,
        0,
    ):
        return today + timedelta(days=1)
    return today


def validate_due_date(due: date, *, now=None) -> None:
    if due is None:
        raise ValueError("Vencimento é obrigatório")
    minimum = min_due_date(now=now)
    today = (timezone.localtime(now) if now is not None else timezone.localtime()).date()
    if due < minimum:
        if minimum > today:
            raise ValueError(
                "Após as 16:00 (horário local), o vencimento deve ser "
                f"a partir de {minimum.strftime('%d/%m/%Y')} (dia seguinte)."
            )
        raise ValueError(
            "Vencimento não pode ser anterior à data atual "
            f"({minimum.strftime('%d/%m/%Y')})."
        )
