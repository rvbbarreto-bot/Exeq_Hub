"""D11 — sync periódico de cobranças abertas."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from apps.billing.due_date_rules import min_due_date
from apps.billing.exceptions import GatewayRegistrationError
from apps.billing.models import Charge
from apps.billing.services import create_charge
from apps.billing.tasks import sync_open_charges, sync_open_charges_task
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
def test_sync_open_charges_calls_gateway_sync(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="sync-batch-1",
        customer=customer,
        amount_cents=5000,
        due_date=min_due_date() + timedelta(days=2),
    )
    assert charge.gateway_ref
    with patch(
        "apps.billing.tasks.sync_charge_from_gateway",
        side_effect=lambda c: c,
    ) as mocked:
        out = sync_open_charges(limit=10)
    assert out["synced"] >= 1
    assert out["errors"] == 0
    assert mocked.called
    synced_ids = {call.args[0].id for call in mocked.call_args_list}
    assert charge.id in synced_ids


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
