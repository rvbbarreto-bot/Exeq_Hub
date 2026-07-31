from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.scheduling.exceptions import (
    InvalidAppointmentTransitionError,
    SlotUnavailableError,
)
from apps.scheduling.models import (
    Appointment,
    BusinessHours,
    Professional,
    ProfessionalService,
    Service,
)
from apps.scheduling.services import (
    cancel_appointment,
    check_in_appointment,
    complete_appointment,
    confirm_appointment,
    create_appointment,
    list_availability_slots,
    start_appointment,
)


@pytest.fixture
def provider(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="11222333000181",
        legal_name="Barbearia ACME",
        tax_regime=TaxRegime.SIMPLES,
    )


@pytest.fixture
def customer(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente Teste",
    )


@pytest.fixture
def professional(tenant_a, provider):
    return Professional.objects.create(
        tenant=tenant_a,
        provider=provider,
        name="João Barbeiro",
        timezone="America/Sao_Paulo",
    )


@pytest.fixture
def service(tenant_a):
    return Service.objects.create(
        tenant=tenant_a,
        name="Corte",
        duration_minutes=30,
        price_cents=5000,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
    )


@pytest.fixture
def linked(tenant_a, professional, service):
    return ProfessionalService.objects.create(
        tenant=tenant_a, professional=professional, service=service
    )


def _next_weekday_at(hour: int, minute: int = 0) -> datetime:
    tz = ZoneInfo("America/Sao_Paulo")
    day = timezone.now().astimezone(tz).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


@pytest.fixture
def business_hours(tenant_a, professional):
    # weekday Sun=0 … Sat=6; cria seg–sex
    rows = []
    for dow in (1, 2, 3, 4, 5):
        rows.append(
            BusinessHours.objects.create(
                tenant=tenant_a,
                professional=professional,
                weekday=dow,
                starts_at=time(9, 0),
                ends_at=time(18, 0),
            )
        )
    return rows


@pytest.mark.django_db
def test_create_confirm_complete_flow(
    tenant_a, customer, professional, service, linked, business_hours
):
    starts = _next_weekday_at(10, 0)
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=starts,
        idempotency_key="flow-001",
        explicit_confirmation=True,
        source=Appointment.Source.ADMIN,
    )
    assert appt.status == Appointment.Status.PENDING
    appt = confirm_appointment(tenant=tenant_a, appointment_id=appt.id)
    assert appt.status == Appointment.Status.CONFIRMED
    appt = check_in_appointment(tenant=tenant_a, appointment_id=appt.id)
    appt = start_appointment(tenant=tenant_a, appointment_id=appt.id)
    appt = complete_appointment(tenant=tenant_a, appointment_id=appt.id)
    assert appt.status == Appointment.Status.COMPLETED


@pytest.mark.django_db
def test_overlap_rejected(
    tenant_a, customer, professional, service, linked, business_hours
):
    starts = _next_weekday_at(11, 0)
    create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=starts,
        idempotency_key="ov-1",
        source=Appointment.Source.ADMIN,
    )
    with pytest.raises(SlotUnavailableError):
        create_appointment(
            tenant=tenant_a,
            customer_id=customer.id,
            professional_id=professional.id,
            service_id=service.id,
            starts_at=starts + timedelta(minutes=15),
            idempotency_key="ov-2",
            source=Appointment.Source.ADMIN,
        )


@pytest.mark.django_db
def test_idempotency_replay(
    tenant_a, customer, professional, service, linked, business_hours
):
    starts = _next_weekday_at(14, 0)
    first = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=starts,
        idempotency_key="idem-1",
    )
    second = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=starts,
        idempotency_key="idem-1",
    )
    assert first.id == second.id


@pytest.mark.django_db
def test_cancel_from_confirmed(
    tenant_a, customer, professional, service, linked, business_hours
):
    starts = _next_weekday_at(15, 0)
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=starts,
        idempotency_key="cancel-1",
    )
    assert appt.status == Appointment.Status.CONFIRMED
    appt = cancel_appointment(tenant=tenant_a, appointment_id=appt.id)
    assert appt.status == Appointment.Status.CANCELLED
    with pytest.raises(InvalidAppointmentTransitionError):
        confirm_appointment(tenant=tenant_a, appointment_id=appt.id)


@pytest.mark.django_db
def test_availability_returns_slots(
    tenant_a, professional, service, linked, business_hours
):
    starts = _next_weekday_at(10, 0)
    day = starts.date()
    slots = list_availability_slots(
        tenant=tenant_a,
        professional_id=professional.id,
        service_id=service.id,
        day=day,
        slot_interval_minutes=30,
    )
    assert len(slots) > 0
    assert any(s.hour == 10 for s in slots)
