"""Regras puras de booking (portadas do barbearia-saas / catalog/booking-rules)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.scheduling.exceptions import (
    AppointmentInPastError,
    ScheduleDurationMismatchError,
    ServicePriceMismatchError,
)
from apps.scheduling.models import Appointment

APPOINTMENT_PAST_GRACE = timedelta(minutes=1)

SLOT_BLOCKING_STATUSES = frozenset(
    {
        Appointment.Status.PENDING,
        Appointment.Status.CONFIRMED,
        Appointment.Status.NO_SHOW_PENDING,
        Appointment.Status.CHECKED_IN,
        Appointment.Status.IN_PROGRESS,
        Appointment.Status.COMPLETED,
    }
)

CONFIRM_FROM = frozenset({Appointment.Status.PENDING})
CHECK_IN_FROM = frozenset(
    {Appointment.Status.CONFIRMED, Appointment.Status.NO_SHOW_PENDING}
)
START_FROM = frozenset({Appointment.Status.CHECKED_IN})
COMPLETE_FROM = frozenset({Appointment.Status.IN_PROGRESS})
NO_SHOW_FROM = frozenset(
    {
        Appointment.Status.PENDING,
        Appointment.Status.CONFIRMED,
        Appointment.Status.NO_SHOW_PENDING,
    }
)
CANCEL_FROM = frozenset(
    {
        Appointment.Status.PENDING,
        Appointment.Status.CONFIRMED,
        Appointment.Status.NO_SHOW_PENDING,
        Appointment.Status.CHECKED_IN,
    }
)


@dataclass(frozen=True)
class BookableService:
    id: object
    duration_minutes: int
    price_cents: int
    buffer_before_minutes: int
    buffer_after_minutes: int


def assert_starts_not_in_past(
    starts_at: datetime, *, now: datetime | None = None
) -> None:
    ref = now or datetime.now(tz=starts_at.tzinfo)
    if starts_at < ref - APPOINTMENT_PAST_GRACE:
        raise AppointmentInPastError("Não é possível agendar no passado.")


def compute_ends_at(starts_at: datetime, duration_minutes: int) -> datetime:
    return starts_at + timedelta(minutes=duration_minutes)


def expand_footprint(
    starts_at: datetime,
    ends_at: datetime,
    buffer_before_minutes: int,
    buffer_after_minutes: int,
) -> tuple[datetime, datetime]:
    return (
        starts_at - timedelta(minutes=buffer_before_minutes),
        ends_at + timedelta(minutes=buffer_after_minutes),
    )


def assert_ends_match_duration(
    *, starts_at: datetime, ends_at: datetime, duration_minutes: int
) -> None:
    expected = compute_ends_at(starts_at, duration_minutes)
    if abs((ends_at - expected).total_seconds()) > 60:
        raise ScheduleDurationMismatchError(
            "Intervalo deve corresponder à duração cadastrada do serviço."
        )


def assert_matching_price(
    declared_price_cents: int | None, catalog_price_cents: int
) -> None:
    if declared_price_cents is None:
        return
    if declared_price_cents != catalog_price_cents:
        raise ServicePriceMismatchError(
            "Valor informado não confere com o preço cadastrado do serviço."
        )


def ranges_overlap(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    """Intervalos semiabertos [start, end)."""
    return a_start < b_end and b_start < a_end
