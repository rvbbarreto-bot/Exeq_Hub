from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.scheduling.models import (
    Appointment,
    AppointmentFinancial,
    BusinessHours,
    CommissionEntry,
    CommissionRule,
    Professional,
    ProfessionalService,
    Service,
)
from apps.scheduling.services import (
    check_in_appointment,
    complete_appointment,
    create_appointment,
    start_appointment,
)
from apps.scheduling.finance import record_deposit, settle_financial


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
        name="Cliente Fin",
    )


@pytest.fixture
def professional(tenant_a, provider):
    return Professional.objects.create(
        tenant=tenant_a,
        provider=provider,
        name="João",
        timezone="America/Sao_Paulo",
    )


@pytest.fixture
def service(tenant_a):
    return Service.objects.create(
        tenant=tenant_a,
        name="Corte",
        duration_minutes=30,
        price_cents=10000,
    )


@pytest.fixture
def bookable(tenant_a, professional, service):
    ProfessionalService.objects.create(
        tenant=tenant_a, professional=professional, service=service
    )
    for dow in (1, 2, 3, 4, 5):
        BusinessHours.objects.create(
            tenant=tenant_a,
            professional=professional,
            weekday=dow,
            starts_at=time(9, 0),
            ends_at=time(18, 0),
        )


def _slot() -> datetime:
    tz = ZoneInfo("America/Sao_Paulo")
    day = timezone.now().astimezone(tz).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(10, 0), tzinfo=tz)


def _complete_flow(tenant_a, customer, professional, service, key: str):
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=_slot(),
        idempotency_key=key,
    )
    check_in_appointment(tenant=tenant_a, appointment_id=appt.id)
    start_appointment(tenant=tenant_a, appointment_id=appt.id)
    return complete_appointment(tenant=tenant_a, appointment_id=appt.id)


@pytest.mark.django_db
def test_complete_creates_financial_and_commission(
    tenant_a, customer, professional, service, bookable
):
    CommissionRule.objects.create(
        tenant=tenant_a,
        rule_kind=CommissionRule.RuleKind.PERCENT,
        percent_basis_points=4000,
        priority=1,
        is_active=True,
    )
    appt = _complete_flow(tenant_a, customer, professional, service, "fin-1")
    assert appt.status == Appointment.Status.COMPLETED
    fin = AppointmentFinancial.objects.get(tenant=tenant_a, appointment=appt)
    assert fin.service_price_cents == 10000
    entry = CommissionEntry.objects.get(tenant=tenant_a, appointment=appt)
    assert entry.commission_cents == 4000
    assert entry.status == CommissionEntry.Status.PENDING


@pytest.mark.django_db
def test_deposit_and_settle(tenant_a, customer, professional, service, bookable):
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=_slot(),
        idempotency_key="fin-dep-1",
    )
    fin = record_deposit(
        tenant=tenant_a, appointment_id=appt.id, deposit_paid_cents=3000
    )
    assert fin.deposit_paid_cents == 3000
    assert fin.balance_due_cents == 7000
    fin = settle_financial(
        tenant=tenant_a,
        appointment_id=appt.id,
        balance_payment_method="pix",
    )
    assert fin.settled_at is not None
    assert fin.balance_due_cents == 7000
