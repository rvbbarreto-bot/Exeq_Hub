from datetime import date

import pytest

from apps.billing.exceptions import InvalidChargeInputError
from apps.billing.models import Charge
from apps.billing.services import create_charge, emit_pending_charge
from apps.master_data.services import create_customer
from apps.ops.models import OutboxMessage


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


@pytest.mark.django_db
def test_emit_pending_charge_registers_gateway(tenant_a, customer):
    orphan = Charge.objects.create(
        tenant=tenant_a,
        idempotency_key="orphan-emit-1",
        customer=customer,
        amount_cents=251,
        due_date=date(2026, 8, 1),
        seu_numero="ORPH01",
        status=Charge.Status.PENDING,
    )
    assert orphan.gateway_ref == ""

    emitted = emit_pending_charge(orphan)
    emitted.refresh_from_db()
    assert emitted.status == Charge.Status.REGISTERED
    assert emitted.gateway_ref.startswith("inter_")
    assert OutboxMessage.objects.filter(
        aggregate_id=emitted.id, event_type="charge.registered"
    ).exists()


@pytest.mark.django_db
def test_create_charge_resumes_pending_without_gateway(tenant_a, customer):
    Charge.objects.create(
        tenant=tenant_a,
        idempotency_key="resume-1",
        customer=customer,
        amount_cents=300,
        due_date=date(2026, 8, 1),
        seu_numero="RES01",
        status=Charge.Status.PENDING,
    )
    result = create_charge(
        tenant=tenant_a,
        idempotency_key="resume-1",
        customer=customer,
        amount_cents=300,
        due_date=date(2026, 8, 1),
        seu_numero="RES01",
    )
    assert result.status == Charge.Status.REGISTERED
    assert result.gateway_ref


@pytest.mark.django_db
def test_emit_pending_rejects_below_min(tenant_a, customer):
    orphan = Charge.objects.create(
        tenant=tenant_a,
        idempotency_key="orphan-low",
        customer=customer,
        amount_cents=200,
        due_date=date(2026, 8, 1),
        seu_numero="LOW01",
        status=Charge.Status.PENDING,
    )
    with pytest.raises(InvalidChargeInputError, match="R\\$ 2,50"):
        emit_pending_charge(orphan)
