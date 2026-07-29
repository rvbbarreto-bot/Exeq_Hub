from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage
from apps.scheduling.models import (
    Appointment,
    BusinessHours,
    Professional,
    ProfessionalService,
    Service,
)
from apps.scheduling.notifications import EVENT_CONFIRMED, EVENT_PENDING
from apps.scheduling.services import confirm_appointment, create_appointment


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
        name="Cliente WA",
        whatsapp="+5511987654321",
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
        price_cents=5000,
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


def _next_slot() -> datetime:
    tz = ZoneInfo("America/Sao_Paulo")
    day = timezone.now().astimezone(tz).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(10, 0), tzinfo=tz)


@pytest.mark.django_db(transaction=True)
def test_create_pending_enqueues_and_dispatches_whatsapp(
    tenant_a, customer, professional, service, bookable
):
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=_next_slot(),
        idempotency_key="wa-pending-1",
        explicit_confirmation=True,
    )
    assert appt.status == Appointment.Status.PENDING
    msg = OutboxMessage.objects.get(
        tenant=tenant_a, aggregate_id=appt.id, event_type=EVENT_PENDING
    )
    assert msg.payload["phone_e164"] == "+5511987654321"
    # Celery eager + on_commit (transaction=True) pode já ter processado
    if msg.status != OutboxMessage.Status.PROCESSED:
        assert claim_and_dispatch(str(msg.id)) == "processed"
    note = ChannelNotification.objects.get(
        tenant=tenant_a, event_type=EVENT_PENDING
    )
    assert note.status == ChannelNotification.Status.SENT
    assert "aguardando confirmação" in note.message_body.lower()


@pytest.mark.django_db(transaction=True)
def test_confirm_enqueues_confirmed_notification(
    tenant_a, customer, professional, service, bookable
):
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=customer.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=_next_slot(),
        idempotency_key="wa-confirm-1",
        explicit_confirmation=True,
    )
    confirm_appointment(tenant=tenant_a, appointment_id=appt.id)
    msg = OutboxMessage.objects.get(
        tenant=tenant_a, aggregate_id=appt.id, event_type=EVENT_CONFIRMED
    )
    if msg.status != OutboxMessage.Status.PROCESSED:
        assert claim_and_dispatch(str(msg.id)) == "processed"
    note = ChannelNotification.objects.get(
        tenant=tenant_a, event_type=EVENT_CONFIRMED
    )
    assert "confirmado" in note.message_body.lower()


@pytest.mark.django_db
def test_no_whatsapp_skips_outbox(
    tenant_a, professional, service, bookable, provider
):
    silent = Customer.objects.create(
        tenant=tenant_a,
        document="98765432100",
        document_type=Customer.DocumentType.CPF,
        name="Sem WA",
        whatsapp="",
    )
    appt = create_appointment(
        tenant=tenant_a,
        customer_id=silent.id,
        professional_id=professional.id,
        service_id=service.id,
        starts_at=_next_slot(),
        idempotency_key="wa-silent-1",
    )
    assert (
        OutboxMessage.objects.filter(tenant=tenant_a, aggregate_id=appt.id).count()
        == 0
    )
