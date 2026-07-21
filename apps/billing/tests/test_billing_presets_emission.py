from datetime import date
from decimal import Decimal

import pytest

from apps.billing.exceptions import InvalidBillingPresetError, InvalidChargeInputError
from apps.billing.message_lines import split_message_lines
from apps.billing.models import Charge
from apps.billing.presets import get_billing_preset, set_billing_preset
from apps.billing.schedule import add_months, seu_numero_for_installment, split_amount_cents
from apps.billing.services import create_charge
from apps.master_data.services import create_customer


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


def test_split_message_lines_caps_at_five():
    lines = split_message_lines("x" * 200)
    assert len(lines) == 5
    assert all(len(line) <= 78 for line in lines)


def test_split_amount_and_seu_numero():
    assert split_amount_cents(1000, 3) == [334, 333, 333]
    assert len(seu_numero_for_installment("CTRL0001", 2, 3)) <= 15


def test_add_months_end_of_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


@pytest.mark.django_db
def test_billing_preset_roundtrip(tenant_a):
    assert get_billing_preset(tenant=tenant_a)["num_dias_agenda"] == 0
    saved = set_billing_preset(
        tenant=tenant_a,
        preset={
            "num_dias_agenda": 30,
            "apply_multa": True,
            "multa_percent": "2.00",
            "apply_mora": True,
            "mora_percent_am": "1.5",
        },
    )
    tenant_a.refresh_from_db()
    assert saved["num_dias_agenda"] == 30
    assert get_billing_preset(tenant=tenant_a)["apply_multa"] is True


@pytest.mark.django_db
def test_billing_preset_rejects_agenda_over_60(tenant_a):
    with pytest.raises(InvalidBillingPresetError):
        set_billing_preset(tenant=tenant_a, preset={"num_dias_agenda": 61})


@pytest.mark.django_db
def test_create_charge_applies_preset_to_inter_fields(tenant_a, customer):
    set_billing_preset(
        tenant=tenant_a,
        preset={
            "num_dias_agenda": 15,
            "apply_multa": True,
            "multa_percent": "2",
            "apply_mora": True,
            "mora_percent_am": "1",
        },
    )
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-preset",
        customer=customer,
        amount_cents=600,
        due_date=date(2026, 8, 1),
        description="Servico",
        seu_numero="CTRL-PRESET",
    )
    assert charge.seu_numero == "CTRL-PRESET"
    assert charge.num_dias_agenda == 15
    assert charge.multa_percent == Decimal("2")
    assert charge.mora_percent_am == Decimal("1")
    assert charge.message_lines[0] == "Servico"


@pytest.mark.django_db
def test_create_installment_charges(tenant_a, customer):
    result = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-parc",
        customer=customer,
        amount_cents=900,
        due_date=date(2026, 8, 1),
        description="Parcelado",
        seu_numero="PARC01",
        charge_kind=Charge.ChargeKind.INSTALLMENT,
        installment_count=3,
    )
    assert isinstance(result, list)
    assert len(result) == 3
    assert [c.amount_cents for c in result] == [300, 300, 300]
    assert [c.due_date for c in result] == [
        date(2026, 8, 1),
        date(2026, 9, 1),
        date(2026, 10, 1),
    ]
    assert result[0].schedule_group_id == result[2].schedule_group_id
    assert result[0].seu_numero == "PARC01-1"
    assert all(c.charge_kind == Charge.ChargeKind.INSTALLMENT for c in result)
    # idempotent replay
    again = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-parc",
        customer=customer,
        amount_cents=900,
        due_date=date(2026, 8, 1),
        seu_numero="PARC01",
        charge_kind=Charge.ChargeKind.INSTALLMENT,
        installment_count=3,
    )
    assert [c.id for c in again] == [c.id for c in result]


@pytest.mark.django_db
def test_create_recurring_by_end_date(tenant_a, customer):
    result = create_charge(
        tenant=tenant_a,
        idempotency_key="chg-rec",
        customer=customer,
        amount_cents=500,
        due_date=date(2026, 1, 10),
        description="Mensalidade",
        seu_numero="REC01",
        charge_kind=Charge.ChargeKind.RECURRING,
        recurrence_end_date=date(2026, 3, 10),
    )
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(c.amount_cents == 500 for c in result)
    assert result[2].due_date == date(2026, 3, 10)


@pytest.mark.django_db
def test_installment_requires_count(tenant_a, customer):
    with pytest.raises(InvalidChargeInputError):
        create_charge(
            tenant=tenant_a,
            idempotency_key="bad-parc",
            customer=customer,
            amount_cents=1000,
            due_date=date(2026, 8, 1),
            seu_numero="X",
            charge_kind=Charge.ChargeKind.INSTALLMENT,
        )


@pytest.mark.django_db
def test_billing_presets_api(api_client, auth_header, tenant_a):
    response = api_client.get("/api/v1/billing/presets", **auth_header)
    assert response.status_code == 200
    assert response.data["num_dias_agenda"] == 0

    put = api_client.put(
        "/api/v1/billing/presets",
        {
            "num_dias_agenda": 10,
            "apply_multa": True,
            "multa_percent": "2.5",
            "apply_mora": False,
            "mora_percent_am": "0",
        },
        format="json",
        **auth_header,
    )
    assert put.status_code == 200
    assert put.data["num_dias_agenda"] == 10
    tenant_a.refresh_from_db()
    assert tenant_a.settings["billing_preset"]["multa_percent"] == "2.5"
