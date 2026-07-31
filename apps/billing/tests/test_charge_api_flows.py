"""Fluxos API Cobrança — integração (cancel / sync / parcelado)."""

from datetime import timedelta

import pytest

from apps.billing.due_date_rules import min_due_date
from apps.billing.models import Charge
from apps.master_data.services import create_customer


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador API",
    )


@pytest.mark.django_db
def test_api_create_installment_envelope(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    due = (min_due_date() + timedelta(days=5)).isoformat()
    res = api_client.post(
        "/api/v1/charges/",
        {
            "idempotency_key": "api-parc-1",
            "customer_id": str(customer.id),
            "amount_cents": 900,
            "due_date": due,
            "description": "Parcelado API",
            "charge_kind": "installment",
            "installment_count": 3,
            "seu_numero": "APIP01",
        },
        format="json",
        **auth_header,
    )
    assert res.status_code == 201, res.data
    assert res.data["charge_kind"] == "installment"
    assert len(res.data["charges"]) == 3
    assert res.data["schedule_group_id"]
    assert Charge.objects.filter(tenant=tenant_a, schedule_group_id=res.data["schedule_group_id"]).count() == 3


@pytest.mark.django_db
def test_api_cancel_and_sync(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    due = (min_due_date() + timedelta(days=4)).isoformat()
    created = api_client.post(
        "/api/v1/charges/",
        {
            "idempotency_key": "api-canc-1",
            "customer_id": str(customer.id),
            "amount_cents": 5000,
            "due_date": due,
            "description": "Cancel API",
        },
        format="json",
        **auth_header,
    )
    assert created.status_code == 201, created.data
    charge_id = created.data["id"]

    synced = api_client.post(
        f"/api/v1/charges/{charge_id}/sync/",
        {},
        format="json",
        **auth_header,
    )
    assert synced.status_code == 200, synced.data

    cancelled = api_client.post(
        f"/api/v1/charges/{charge_id}/cancel/",
        {"motivo_cancelamento": "SUBSTITUICAO"},
        format="json",
        **auth_header,
    )
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["status"] == "cancelled"
