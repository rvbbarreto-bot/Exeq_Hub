import pytest
from datetime import date

from apps.billing.admin import ChargeAdminForm
from apps.billing.amount_rules import CHARGE_MIN_AMOUNT_CENTS, validate_charge_amount_cents
from apps.billing.exceptions import InvalidChargeInputError
from apps.billing.models import Charge
from apps.billing.services import create_charge
from apps.master_data.services import create_customer


def test_validate_charge_amount_rejects_below_min():
    with pytest.raises(ValueError, match="R\\$ 2,50"):
        validate_charge_amount_cents(249)
    validate_charge_amount_cents(CHARGE_MIN_AMOUNT_CENTS)


@pytest.mark.django_db
def test_admin_form_shows_field_error_for_low_amount(tenant_a):
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )
    form = ChargeAdminForm(
        data={
            "tenant": tenant_a.id,
            "idempotency_key": "amt-low",
            "customer": customer.id,
            "valor_reais": "2,00",
            "due_date": "2026-08-01",
            "charge_kind": Charge.ChargeKind.SIMPLE,
            "billing_type": "BOLETO",
            "description": "",
            "seu_numero": "T001",
        }
    )
    assert form.is_valid() is False
    assert "valor_reais" in form.errors
    assert "R$ 2,50" in form.errors["valor_reais"][0]


@pytest.mark.django_db
def test_admin_idempotency_key_readonly_and_auto():
    from apps.billing.admin import ChargeAdminForm, _new_admin_idempotency_key

    key = _new_admin_idempotency_key()
    assert key.startswith("admin-")
    form = ChargeAdminForm()
    assert form.fields["idempotency_key"].widget.attrs.get("readonly") is True
    assert form.fields["idempotency_key"].initial
    assert str(form.fields["idempotency_key"].initial).startswith("admin-")


@pytest.mark.django_db
def test_create_charge_rejects_below_min(tenant_a):
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )
    with pytest.raises(InvalidChargeInputError, match="R\\$ 2,50"):
        create_charge(
            tenant=tenant_a,
            idempotency_key="amt-api",
            customer=customer,
            amount_cents=200,
            due_date=date(2026, 8, 1),
            seu_numero="T002",
        )
