from datetime import time, timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.scheduling.models import (
    Appointment,
    BusinessHours,
    CalendarBlock,
    CommissionRule,
    CustomerRestriction,
    Professional,
    ProfessionalService,
    RecurringTimeOff,
    Service,
    TimeOff,
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
    )


@pytest.fixture
def service(tenant_a):
    return Service.objects.create(
        tenant=tenant_a,
        name="Corte",
        duration_minutes=30,
        price_cents=5000,
    )


@pytest.mark.django_db
def test_professional_str_and_create(professional):
    assert str(professional) == "João Barbeiro"
    assert professional.timezone == "America/Sao_Paulo"
    assert professional.is_active is True


@pytest.mark.django_db
def test_service_str_and_create(service):
    assert str(service) == "Corte"
    assert service.buffer_before_minutes == 0


@pytest.mark.django_db
def test_professional_service_unique(tenant_a, professional, service):
    ProfessionalService.objects.create(
        tenant=tenant_a, professional=professional, service=service
    )
    with pytest.raises(IntegrityError):
        ProfessionalService.objects.create(
            tenant=tenant_a, professional=professional, service=service
        )


@pytest.mark.django_db
def test_business_hours_create(tenant_a, professional):
    row = BusinessHours.objects.create(
        tenant=tenant_a,
        professional=professional,
        weekday=1,
        starts_at=time(9, 0),
        ends_at=time(18, 0),
    )
    assert "wd=1" in str(row)


@pytest.mark.django_db
def test_time_off_and_recurring(tenant_a, professional):
    start = timezone.now()
    off = TimeOff.objects.create(
        tenant=tenant_a,
        professional=professional,
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        reason="Férias",
    )
    assert off.reason == "Férias"
    recur = RecurringTimeOff.objects.create(
        tenant=tenant_a,
        professional=professional,
        weekday=0,
        starts_at=time(12, 0),
        ends_at=time(13, 0),
    )
    assert recur.weekday == 0


@pytest.mark.django_db
def test_calendar_block_create(tenant_a, professional, user_ana):
    start = timezone.now()
    block = CalendarBlock.objects.create(
        tenant=tenant_a,
        professional=professional,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        reason="Manutenção",
        created_by=user_ana,
    )
    assert block.created_by_id == user_ana.id


@pytest.mark.django_db
def test_appointment_create(tenant_a, professional, customer, service):
    start = timezone.now() + timedelta(days=1)
    appt = Appointment.objects.create(
        tenant=tenant_a,
        professional=professional,
        customer=customer,
        service=service,
        starts_at=start,
        ends_at=start + timedelta(minutes=30),
        price_cents=5000,
        status=Appointment.Status.CONFIRMED,
        source=Appointment.Source.WHATSAPP,
        idempotency_key="appt-basic-001",
    )
    assert appt.status == Appointment.Status.CONFIRMED
    assert customer.name in str(appt)


@pytest.mark.django_db
def test_customer_restriction_one_to_one(tenant_a, customer):
    CustomerRestriction.objects.create(
        tenant=tenant_a,
        customer=customer,
        requires_deposit=True,
        manual_booking_only=True,
    )
    with pytest.raises(IntegrityError):
        CustomerRestriction.objects.create(
            tenant=tenant_a,
            customer=customer,
            requires_deposit=False,
        )


@pytest.mark.django_db
def test_commission_rule_percent_and_fixed(tenant_a, professional, service):
    percent = CommissionRule.objects.create(
        tenant=tenant_a,
        professional=professional,
        service=service,
        rule_kind=CommissionRule.RuleKind.PERCENT,
        percent_basis_points=4000,
        priority=10,
    )
    assert "percent" in str(percent)
    fixed = CommissionRule.objects.create(
        tenant=tenant_a,
        rule_kind=CommissionRule.RuleKind.FIXED_CENTS,
        fixed_cents=1500,
        priority=0,
    )
    assert fixed.fixed_cents == 1500
