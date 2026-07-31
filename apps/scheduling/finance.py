"""Financeiro operacional + comissão (split operacional — ledger)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.scheduling.commission_resolution import (
    CommissionRuleView,
    compute_commission_cents,
    resolve_best_commission_rule,
)
from apps.scheduling.exceptions import (
    AppointmentNotFoundError,
    InvalidAppointmentTransitionError,
    SchedulingError,
)
from apps.scheduling.models import (
    Appointment,
    AppointmentFinancial,
    CommissionEntry,
    CommissionRule,
)


class FinancialError(SchedulingError):
    code = "financial_error"


class CommissionEntryNotFoundError(SchedulingError):
    code = "commission_entry_not_found"


def balance_due_cents(fin: AppointmentFinancial) -> int:
    return fin.balance_due_cents


@transaction.atomic
def ensure_financial_on_completed(*, tenant, appointment: Appointment) -> AppointmentFinancial:
    """Garante snapshot financeiro ao concluir (idempotente)."""
    price = int(appointment.price_cents or 0)

    fin, created = AppointmentFinancial.objects.select_for_update().get_or_create(
        tenant=tenant,
        appointment=appointment,
        defaults={
            "service_price_cents": price,
            "deposit_paid_cents": 0,
            "discount_cents": 0,
        },
    )
    if created:
        return fin
    if fin.settled_at is None and fin.service_price_cents != price:
        fin.service_price_cents = price
        fin.save(update_fields=["service_price_cents", "updated_at"])
    return fin


@transaction.atomic
def record_deposit(
    *,
    tenant,
    appointment_id,
    deposit_paid_cents: int,
) -> AppointmentFinancial:
    if deposit_paid_cents < 0:
        raise FinancialError("Sinal não pode ser negativo.")
    try:
        appt = Appointment.objects.select_related("service").get(
            tenant=tenant, pk=appointment_id
        )
    except Appointment.DoesNotExist as exc:
        raise AppointmentNotFoundError("Agendamento não encontrado.") from exc

    fin, _ = AppointmentFinancial.objects.select_for_update().get_or_create(
        tenant=tenant,
        appointment=appt,
        defaults={
            "service_price_cents": int(appt.price_cents or 0),
            "deposit_paid_cents": 0,
            "discount_cents": 0,
        },
    )
    if fin.settled_at is not None:
        raise FinancialError("Financeiro já liquidado.")
    if deposit_paid_cents + fin.discount_cents > fin.service_price_cents:
        raise FinancialError("Sinal + desconto excedem o preço do serviço.")
    fin.deposit_paid_cents = deposit_paid_cents
    fin.deposit_recorded_at = timezone.now()
    fin.save(
        update_fields=["deposit_paid_cents", "deposit_recorded_at", "updated_at"]
    )
    return fin


@transaction.atomic
def settle_financial(
    *,
    tenant,
    appointment_id,
    balance_payment_method: str = "",
    discount_cents: int = 0,
    discount_reason: str = "",
) -> AppointmentFinancial:
    if discount_cents < 0:
        raise FinancialError("Desconto não pode ser negativo.")
    try:
        appt = Appointment.objects.get(tenant=tenant, pk=appointment_id)
    except Appointment.DoesNotExist as exc:
        raise AppointmentNotFoundError("Agendamento não encontrado.") from exc

    fin, _ = AppointmentFinancial.objects.select_for_update().get_or_create(
        tenant=tenant,
        appointment=appt,
        defaults={
            "service_price_cents": int(appt.price_cents or 0),
            "deposit_paid_cents": 0,
            "discount_cents": 0,
        },
    )
    if fin.settled_at is not None:
        return fin
    if discount_cents and not discount_reason.strip():
        raise FinancialError("Motivo do desconto é obrigatório quando há desconto.")
    if fin.deposit_paid_cents + discount_cents > fin.service_price_cents:
        raise FinancialError("Sinal + desconto excedem o preço do serviço.")
    fin.discount_cents = discount_cents
    fin.discount_reason = discount_reason.strip() if discount_cents else ""
    if balance_payment_method:
        fin.balance_payment_method = balance_payment_method
    fin.settled_at = timezone.now()
    fin.save(
        update_fields=[
            "discount_cents",
            "discount_reason",
            "balance_payment_method",
            "settled_at",
            "updated_at",
        ]
    )
    return fin


def _rules_as_views(*, tenant) -> list[CommissionRuleView]:
    rows = CommissionRule.objects.filter(tenant=tenant, is_active=True)
    return [
        CommissionRuleView(
            id=r.id,
            branch_id=r.branch_id,
            professional_id=r.professional_id,
            service_id=r.service_id,
            rule_kind=r.rule_kind,
            percent_basis_points=r.percent_basis_points,
            fixed_cents=r.fixed_cents,
            priority=r.priority,
        )
        for r in rows
    ]


@transaction.atomic
def create_commission_entry_for_completed(
    *, tenant, appointment: Appointment
) -> CommissionEntry | None:
    """Idempotente: um lançamento por agendamento. Só faz sentido se completed."""
    if appointment.status != Appointment.Status.COMPLETED:
        return None

    existing = CommissionEntry.objects.filter(
        tenant=tenant, appointment=appointment
    ).first()
    if existing:
        return existing

    fin = AppointmentFinancial.objects.filter(
        tenant=tenant, appointment=appointment
    ).first()
    base = (
        int(fin.service_price_cents)
        if fin is not None
        else int(appointment.price_cents or 0)
    )

    best = resolve_best_commission_rule(
        branch_id=None,
        professional_id=appointment.professional_id,
        service_id=appointment.service_id,
        rules=_rules_as_views(tenant=tenant),
    )
    commission_cents = (
        compute_commission_cents(base_amount_cents=base, rule=best) if best else 0
    )
    return CommissionEntry.objects.create(
        tenant=tenant,
        appointment=appointment,
        professional_id=appointment.professional_id,
        service_id=appointment.service_id,
        branch_id=None,
        commission_rule_id=best.id if best else None,
        base_amount_cents=base,
        commission_cents=commission_cents,
        status=CommissionEntry.Status.PENDING,
    )


@transaction.atomic
def set_commission_entry_status(
    *, tenant, entry_id, status: str
) -> CommissionEntry:
    allowed = {c.value for c in CommissionEntry.Status}
    if status not in allowed:
        raise FinancialError(f"Status de comissão inválido: {status}")
    try:
        entry = CommissionEntry.objects.select_for_update().get(
            tenant=tenant, pk=entry_id
        )
    except CommissionEntry.DoesNotExist as exc:
        raise CommissionEntryNotFoundError("Lançamento não encontrado.") from exc
    if entry.status == CommissionEntry.Status.CANCELLED and status != entry.status:
        raise InvalidAppointmentTransitionError(
            "Lançamento cancelado não pode mudar de status."
        )
    entry.status = status
    entry.save(update_fields=["status", "updated_at"])
    return entry


@transaction.atomic
def on_appointment_completed(*, tenant, appointment: Appointment) -> None:
    ensure_financial_on_completed(tenant=tenant, appointment=appointment)
    create_commission_entry_for_completed(tenant=tenant, appointment=appointment)
