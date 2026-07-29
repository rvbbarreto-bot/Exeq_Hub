from datetime import time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.scheduling.models import BusinessHours, Professional, ProfessionalService, Service


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
        name="Cliente API",
    )


@pytest.fixture
def professional(tenant_a, provider):
    return Professional.objects.create(
        tenant=tenant_a,
        provider=provider,
        name="Maria",
        timezone="America/Sao_Paulo",
    )


@pytest.fixture
def service(tenant_a):
    return Service.objects.create(
        tenant=tenant_a,
        name="Barba",
        duration_minutes=30,
        price_cents=4000,
    )


@pytest.fixture
def setup_bookable(tenant_a, professional, service):
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


def _next_slot():
    tz = ZoneInfo("America/Sao_Paulo")
    now = timezone.now().astimezone(tz)
    day = now.date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    from datetime import datetime

    return datetime.combine(day, time(10, 0), tzinfo=tz)


@pytest.mark.django_db
def test_api_create_and_confirm_appointment(
    api_client, auth_header, tenant_a, customer, professional, service, setup_bookable
):
    starts = _next_slot()
    create = api_client.post(
        "/api/v1/scheduling/appointments/",
        {
            "customer_id": str(customer.id),
            "professional_id": str(professional.id),
            "service_id": str(service.id),
            "starts_at": starts.isoformat(),
            "idempotency_key": "api-appt-001",
            "explicit_confirmation": True,
            "source": "admin",
        },
        format="json",
        **auth_header,
    )
    assert create.status_code == 201, create.content
    appt_id = create.data["id"]
    assert create.data["status"] == "pending"

    confirm = api_client.post(
        f"/api/v1/scheduling/appointments/{appt_id}/confirm/",
        {},
        format="json",
        **auth_header,
    )
    assert confirm.status_code == 200
    assert confirm.data["status"] == "confirmed"

    listed = api_client.get(
        "/api/v1/scheduling/appointments/",
        **auth_header,
    )
    assert listed.status_code == 200
    assert listed.data["count"] >= 1


@pytest.mark.django_db
def test_api_professionals_list_create(
    api_client, auth_header, tenant_a, provider
):
    response = api_client.post(
        "/api/v1/scheduling/professionals/",
        {
            "provider": str(provider.id),
            "name": "Novo Pro",
            "timezone": "America/Sao_Paulo",
            "is_active": True,
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 201, response.content
    listed = api_client.get("/api/v1/scheduling/professionals/", **auth_header)
    assert listed.status_code == 200
    assert listed.data["count"] >= 1


@pytest.mark.django_db
def test_api_availability(
    api_client, auth_header, professional, service, setup_bookable
):
    day = _next_slot().date().isoformat()
    response = api_client.get(
        "/api/v1/scheduling/availability",
        {
            "professional_id": str(professional.id),
            "service_id": str(service.id),
            "day": day,
        },
        **auth_header,
    )
    assert response.status_code == 200, response.content
    assert "slots" in response.data
    assert len(response.data["slots"]) > 0
