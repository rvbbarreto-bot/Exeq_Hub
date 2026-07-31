"""Mark overdue by due_date + periodic sync job."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.billing.due_date_rules import min_due_date
from apps.billing.exceptions import GatewayRegistrationError
from apps.billing.models import Charge
from apps.billing.services import create_charge, mark_overdue_charges
from apps.billing.tasks import sync_open_charges
from apps.master_data.services import create_customer


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador Sync",
    )


@pytest.mark.django_db
def test_mark_overdue_by_due_date(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    past = timezone.localdate() - timedelta(days=3)
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="overdue-local-1",
        customer=customer,
        amount_cents=251,
        due_date=min_due_date() + timedelta(days=2),
    )
    Charge.objects.filter(pk=charge.pk).update(
        due_date=past,
        status=Charge.Status.REGISTERED,
    )
    out = mark_overdue_charges(tenant=tenant_a)
    assert out["marked_overdue"] >= 1
    charge.refresh_from_db()
    assert charge.status == Charge.Status.OVERDUE


@pytest.mark.django_db
def test_mark_overdue_skips_paid(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    past = timezone.localdate() - timedelta(days=5)
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="overdue-paid-1",
        customer=customer,
        amount_cents=3000,
        due_date=min_due_date() + timedelta(days=2),
    )
    Charge.objects.filter(pk=charge.pk).update(
        due_date=past,
        status=Charge.Status.PAID,
    )
    mark_overdue_charges(tenant=tenant_a)
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID


@pytest.mark.django_db
def test_sync_open_charges_marks_overdue_then_syncs(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    past = timezone.localdate() - timedelta(days=2)
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="sync-batch-od-1",
        customer=customer,
        amount_cents=5000,
        due_date=min_due_date() + timedelta(days=2),
    )
    Charge.objects.filter(pk=charge.pk).update(
        due_date=past,
        status=Charge.Status.REGISTERED,
    )
    with patch(
        "apps.billing.tasks.sync_charge_from_gateway",
        side_effect=lambda c: c,
    ) as mocked:
        out = sync_open_charges(limit=10)
    assert out["marked_overdue"] >= 1
    assert out["synced"] >= 1
    assert out["errors"] == 0
    assert mocked.called
    charge.refresh_from_db()
    assert charge.status == Charge.Status.OVERDUE


@pytest.mark.django_db
def test_sync_open_charges_counts_errors(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    create_charge(
        tenant=tenant_a,
        idempotency_key="sync-err-1",
        customer=customer,
        amount_cents=2500,
        due_date=min_due_date() + timedelta(days=2),
    )
    with patch(
        "apps.billing.tasks.sync_charge_from_gateway",
        side_effect=GatewayRegistrationError("falha gateway"),
    ):
        out = sync_open_charges(limit=10)
    assert out["synced"] == 0
    assert out["errors"] >= 1


@pytest.mark.django_db
def test_charges_list_marks_overdue(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    past = timezone.localdate() - timedelta(days=1)
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="list-od-1",
        customer=customer,
        amount_cents=251,
        due_date=min_due_date() + timedelta(days=2),
    )
    Charge.objects.filter(pk=charge.pk).update(
        due_date=past,
        status=Charge.Status.PENDING,
    )
    res = api_client.get("/api/v1/charges/?page_size=50", **auth_header)
    assert res.status_code == 200
    charge.refresh_from_db()
    assert charge.status == Charge.Status.OVERDUE
