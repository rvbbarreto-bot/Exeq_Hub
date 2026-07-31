"""Application services — EXEQ Agendador (Sprint 2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.master_data.models import Customer
from apps.scheduling.booking_rules import (
    CANCEL_FROM,
    CHECK_IN_FROM,
    COMPLETE_FROM,
    CONFIRM_FROM,
    NO_SHOW_FROM,
    SLOT_BLOCKING_STATUSES,
    START_FROM,
    BookableService,
    assert_ends_match_duration,
    assert_matching_price,
    assert_starts_not_in_past,
    compute_ends_at,
    expand_footprint,
    ranges_overlap,
)
from apps.scheduling.exceptions import (
    AppointmentInPastError,
    AppointmentNotFoundError,
    CustomerNotFoundError,
    CustomerRestrictedError,
    DuplicateIdempotencyKeyError,
    InvalidAppointmentTransitionError,
    ProfessionalNotFoundError,
    ServiceNotBookableError,
    SlotUnavailableError,
)
from apps.scheduling.models import (
    Appointment,
    BusinessHours,
    CalendarBlock,
    CustomerRestriction,
    Professional,
    ProfessionalService,
    RecurringTimeOff,
    TimeOff,
)


def load_bookable_service(
    *, tenant, professional: Professional, service_id
) -> BookableService:
    link = (
        ProfessionalService.objects.filter(
            tenant=tenant,
            professional=professional,
            service_id=service_id,
            service__is_active=True,
        )
        .select_related("service")
        .first()
    )
    if link is None:
        raise ServiceNotBookableError(
            "Serviço inexistente ou não habilitado para este profissional."
        )
    svc = link.service
    return BookableService(
        id=svc.id,
        duration_minutes=svc.duration_minutes,
        price_cents=svc.price_cents,
        buffer_before_minutes=svc.buffer_before_minutes,
        buffer_after_minutes=svc.buffer_after_minutes,
    )


def _tz(professional: Professional) -> ZoneInfo:
    try:
        return ZoneInfo(professional.timezone or "America/Sao_Paulo")
    except Exception:
        return ZoneInfo("America/Sao_Paulo")


def _to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt.astimezone(tz)


def assert_fits_business_hours(
    *, tenant, professional: Professional, starts_at: datetime, ends_at: datetime
) -> None:
    tz = _tz(professional)
    local_start = _to_local(starts_at, tz)
    local_end = _to_local(ends_at, tz)
    if local_start.date() != local_end.date():
        raise SlotUnavailableError(
            "Horário fora do expediente ou indisponível neste dia."
        )
    dow = (local_start.weekday() + 1) % 7  # Sun=0 … Sat=6 (paridade PG DOW)

    qs = BusinessHours.objects.filter(tenant=tenant, weekday=dow)
    hours = list(qs.filter(professional=professional))
    if not hours:
        hours = list(qs.filter(professional__isnull=True))
    if not hours:
        raise SlotUnavailableError(
            "Horário fora do expediente ou indisponível neste dia."
        )
    st = local_start.time()
    et = local_end.time()
    if not any(h.starts_at <= st and et <= h.ends_at for h in hours):
        raise SlotUnavailableError(
            "Horário fora do expediente ou indisponível neste dia."
        )


def assert_clear_of_blocks_and_time_off(
    *,
    tenant,
    professional: Professional,
    footprint_start: datetime,
    footprint_end: datetime,
) -> None:
    blocks = CalendarBlock.objects.filter(
        tenant=tenant,
        professional=professional,
        starts_at__lt=footprint_end,
        ends_at__gt=footprint_start,
    )
    if blocks.exists():
        raise SlotUnavailableError("Horário coberto por bloqueio manual de agenda.")

    offs = TimeOff.objects.filter(
        tenant=tenant,
        professional=professional,
        starts_at__lt=footprint_end,
        ends_at__gt=footprint_start,
    )
    if offs.exists():
        raise SlotUnavailableError("Horário coberto por folga do profissional.")

    tz = _tz(professional)
    local_start = _to_local(footprint_start, tz)
    local_end = _to_local(footprint_end, tz)
    if local_start.date() == local_end.date():
        dow = (local_start.weekday() + 1) % 7
        recurring = RecurringTimeOff.objects.filter(
            tenant=tenant, professional=professional, weekday=dow
        )
        for r in recurring:
            r_start = datetime.combine(local_start.date(), r.starts_at, tzinfo=tz)
            r_end = datetime.combine(local_start.date(), r.ends_at, tzinfo=tz)
            if ranges_overlap(footprint_start, footprint_end, r_start, r_end):
                raise SlotUnavailableError(
                    "Horário coberto por folga recorrente do profissional."
                )


def assert_no_appointment_conflict(
    *,
    tenant,
    professional: Professional,
    footprint_start: datetime,
    footprint_end: datetime,
    exclude_appointment_id=None,
) -> None:
    qs = (
        Appointment.objects.filter(
            tenant=tenant,
            professional=professional,
            status__in=SLOT_BLOCKING_STATUSES,
        )
        .select_related("service")
        .exclude(pk=exclude_appointment_id)
    )
    for appt in qs:
        buf_b = appt.service.buffer_before_minutes if appt.service_id else 0
        buf_a = appt.service.buffer_after_minutes if appt.service_id else 0
        a_start, a_end = expand_footprint(
            appt.starts_at, appt.ends_at, buf_b, buf_a
        )
        if ranges_overlap(footprint_start, footprint_end, a_start, a_end):
            raise SlotUnavailableError(
                "Horário indisponível para este profissional."
            )


def assert_customer_booking_allowed(
    *, tenant, customer: Customer, is_staff: bool
) -> None:
    try:
        restriction = CustomerRestriction.objects.get(tenant=tenant, customer=customer)
    except CustomerRestriction.DoesNotExist:
        return
    if is_staff:
        return
    if restriction.manual_booking_only:
        raise CustomerRestrictedError(
            "Este cliente requer aprovação humana para agendar."
        )
    if restriction.requires_deposit:
        raise CustomerRestrictedError(
            "Cliente sujeito a sinal — agendamento automático indisponível."
        )


def _initial_status(*, explicit_confirmation: bool) -> str:
    if explicit_confirmation:
        return Appointment.Status.PENDING
    return Appointment.Status.CONFIRMED


@transaction.atomic
def create_appointment(
    *,
    tenant,
    customer_id,
    professional_id,
    service_id,
    starts_at: datetime,
    ends_at: datetime | None = None,
    price_cents: int | None = None,
    source: str = Appointment.Source.ADMIN,
    idempotency_key: str,
    notes: str = "",
    explicit_confirmation: bool = False,
    is_staff: bool = True,
) -> Appointment:
    existing = (
        Appointment.objects.filter(tenant=tenant, idempotency_key=idempotency_key)
        .select_related("professional", "customer", "service")
        .first()
    )
    if existing is not None:
        same = (
            str(existing.customer_id) == str(customer_id)
            and str(existing.professional_id) == str(professional_id)
            and str(existing.service_id) == str(service_id)
            and existing.starts_at == starts_at
            and (ends_at is None or existing.ends_at == ends_at)
            and existing.source == source
            and (existing.notes or "") == (notes or "")
        )
        if not same:
            raise DuplicateIdempotencyKeyError(
                "idempotency_key já utilizada para este tenant."
            )
        return existing

    try:
        professional = Professional.objects.select_for_update().get(
            tenant=tenant, pk=professional_id, is_active=True
        )
    except Professional.DoesNotExist as exc:
        raise ProfessionalNotFoundError("Profissional não encontrado.") from exc

    try:
        customer = Customer.objects.get(tenant=tenant, pk=customer_id, is_active=True)
    except Customer.DoesNotExist as exc:
        raise CustomerNotFoundError("Cliente não encontrado.") from exc

    assert_starts_not_in_past(starts_at)
    assert_customer_booking_allowed(
        tenant=tenant, customer=customer, is_staff=is_staff
    )

    bookable = load_bookable_service(
        tenant=tenant, professional=professional, service_id=service_id
    )
    resolved_ends = ends_at or compute_ends_at(starts_at, bookable.duration_minutes)
    assert_ends_match_duration(
        starts_at=starts_at,
        ends_at=resolved_ends,
        duration_minutes=bookable.duration_minutes,
    )
    assert_matching_price(price_cents, bookable.price_cents)

    assert_fits_business_hours(
        tenant=tenant,
        professional=professional,
        starts_at=starts_at,
        ends_at=resolved_ends,
    )
    fp_start, fp_end = expand_footprint(
        starts_at,
        resolved_ends,
        bookable.buffer_before_minutes,
        bookable.buffer_after_minutes,
    )
    assert_clear_of_blocks_and_time_off(
        tenant=tenant,
        professional=professional,
        footprint_start=fp_start,
        footprint_end=fp_end,
    )
    assert_no_appointment_conflict(
        tenant=tenant,
        professional=professional,
        footprint_start=fp_start,
        footprint_end=fp_end,
    )

    appt = Appointment.objects.create(
        tenant=tenant,
        professional=professional,
        customer=customer,
        service_id=bookable.id,
        starts_at=starts_at,
        ends_at=resolved_ends,
        price_cents=bookable.price_cents if price_cents is None else price_cents,
        status=_initial_status(explicit_confirmation=explicit_confirmation),
        source=source,
        explicit_confirmation=explicit_confirmation,
        notes=notes or "",
        idempotency_key=idempotency_key,
    )
    appt = (
        Appointment.objects.select_related("customer", "professional", "service")
        .get(pk=appt.pk)
    )
    from apps.scheduling.notifications import enqueue_for_created_appointment

    enqueue_for_created_appointment(appt)
    return appt


def _get_appointment(*, tenant, appointment_id) -> Appointment:
    try:
        return (
            Appointment.objects.select_for_update()
            .select_related("customer", "professional", "service")
            .get(tenant=tenant, pk=appointment_id)
        )
    except Appointment.DoesNotExist as exc:
        raise AppointmentNotFoundError("Agendamento não encontrado.") from exc


def _transition(
    *, tenant, appointment_id, allowed: frozenset[str], new_status: str
) -> Appointment:
    with transaction.atomic():
        appt = _get_appointment(tenant=tenant, appointment_id=appointment_id)
        if appt.status == new_status:
            return appt
        if appt.status not in allowed:
            raise InvalidAppointmentTransitionError(
                f"Transição não permitida a partir de '{appt.status}'."
            )
        appt.status = new_status
        appt.save(update_fields=["status", "updated_at"])
        from apps.scheduling.notifications import (
            enqueue_appointment_event,
            event_type_for_status,
        )

        event_type = event_type_for_status(new_status)
        if event_type:
            enqueue_appointment_event(appointment=appt, event_type=event_type)
        return appt


@transaction.atomic
def confirm_appointment(*, tenant, appointment_id) -> Appointment:
    return _transition(
        tenant=tenant,
        appointment_id=appointment_id,
        allowed=CONFIRM_FROM,
        new_status=Appointment.Status.CONFIRMED,
    )


@transaction.atomic
def cancel_appointment(*, tenant, appointment_id) -> Appointment:
    return _transition(
        tenant=tenant,
        appointment_id=appointment_id,
        allowed=CANCEL_FROM,
        new_status=Appointment.Status.CANCELLED,
    )


@transaction.atomic
def check_in_appointment(*, tenant, appointment_id) -> Appointment:
    return _transition(
        tenant=tenant,
        appointment_id=appointment_id,
        allowed=CHECK_IN_FROM,
        new_status=Appointment.Status.CHECKED_IN,
    )


@transaction.atomic
def start_appointment(*, tenant, appointment_id) -> Appointment:
    return _transition(
        tenant=tenant,
        appointment_id=appointment_id,
        allowed=START_FROM,
        new_status=Appointment.Status.IN_PROGRESS,
    )


@transaction.atomic
def complete_appointment(*, tenant, appointment_id) -> Appointment:
    appt = _transition(
        tenant=tenant,
        appointment_id=appointment_id,
        allowed=COMPLETE_FROM,
        new_status=Appointment.Status.COMPLETED,
    )
    from apps.scheduling.finance import on_appointment_completed

    on_appointment_completed(tenant=tenant, appointment=appt)
    return appt



@transaction.atomic
def mark_no_show(*, tenant, appointment_id) -> Appointment:
    return _transition(
        tenant=tenant,
        appointment_id=appointment_id,
        allowed=NO_SHOW_FROM,
        new_status=Appointment.Status.NO_SHOW,
    )


def list_availability_slots(
    *,
    tenant,
    professional_id,
    service_id,
    day: date,
    slot_interval_minutes: int = 30,
) -> list[datetime]:
    """Slots nominais livres no dia (timezone do profissional)."""
    try:
        professional = Professional.objects.get(
            tenant=tenant, pk=professional_id, is_active=True
        )
    except Professional.DoesNotExist as exc:
        raise ProfessionalNotFoundError("Profissional não encontrado.") from exc

    bookable = load_bookable_service(
        tenant=tenant, professional=professional, service_id=service_id
    )
    tz = _tz(professional)
    dow = (day.weekday() + 1) % 7
    qs = BusinessHours.objects.filter(tenant=tenant, weekday=dow)
    hours = list(qs.filter(professional=professional))
    if not hours:
        hours = list(qs.filter(professional__isnull=True))
    if not hours:
        return []

    now = timezone.now()
    slots: list[datetime] = []
    for h in hours:
        cursor = datetime.combine(day, h.starts_at, tzinfo=tz)
        day_end = datetime.combine(day, h.ends_at, tzinfo=tz)
        while True:
            ends = compute_ends_at(cursor, bookable.duration_minutes)
            if ends > day_end:
                break
            try:
                assert_starts_not_in_past(cursor, now=now)
                assert_fits_business_hours(
                    tenant=tenant,
                    professional=professional,
                    starts_at=cursor,
                    ends_at=ends,
                )
                fp_s, fp_e = expand_footprint(
                    cursor,
                    ends,
                    bookable.buffer_before_minutes,
                    bookable.buffer_after_minutes,
                )
                assert_clear_of_blocks_and_time_off(
                    tenant=tenant,
                    professional=professional,
                    footprint_start=fp_s,
                    footprint_end=fp_e,
                )
                assert_no_appointment_conflict(
                    tenant=tenant,
                    professional=professional,
                    footprint_start=fp_s,
                    footprint_end=fp_e,
                )
                slots.append(cursor)
            except (SlotUnavailableError, AppointmentInPastError):
                pass
            cursor += timedelta(minutes=slot_interval_minutes)
    return slots
