from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.billing.admin import ChargeAdminForm
from apps.billing.due_date_rules import min_due_date, validate_due_date
from apps.billing.exceptions import InvalidChargeInputError
from apps.billing.models import Charge
from apps.billing.services import create_charge
from apps.master_data.services import create_customer


TZ = ZoneInfo("America/Sao_Paulo")


def _at(hour: int, minute: int = 0, day: date | None = None):
    d = day or date(2026, 7, 21)
    return timezone.make_aware(datetime(d.year, d.month, d.day, hour, minute), TZ)


def test_min_due_date_before_cutoff_is_today():
    now = _at(15, 59)
    assert min_due_date(now=now) == date(2026, 7, 21)


def test_min_due_date_at_and_after_cutoff_is_tomorrow():
    assert min_due_date(now=_at(16, 0)) == date(2026, 7, 22)
    assert min_due_date(now=_at(18, 30)) == date(2026, 7, 22)


def test_validate_due_date_rejects_past():
    with pytest.raises(ValueError, match="anterior"):
        validate_due_date(date(2026, 7, 20), now=_at(10, 0))


def test_validate_due_date_rejects_today_after_cutoff():
    with pytest.raises(ValueError, match="16:00"):
        validate_due_date(date(2026, 7, 21), now=_at(16, 1))


def test_validate_due_date_allows_tomorrow_after_cutoff():
    validate_due_date(date(2026, 7, 22), now=_at(16, 1))


@pytest.mark.django_db
def test_admin_form_rejects_alpha_in_schedule_fields(tenant_a):
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )
    form = ChargeAdminForm(
        data={
            "tenant": tenant_a.id,
            "idempotency_key": "num-alpha",
            "customer": customer.id,
            "valor_reais": "6,00",
            "due_date": "2026-08-01",
            "charge_kind": Charge.ChargeKind.SIMPLE,
            "billing_type": "BOLETO",
            "description": "",
            "seu_numero": "T001",
            "num_dias_agenda": "e",
            "multa_percent": "e",
            "mora_percent_am": "abc",
        }
    )
    assert form.is_valid() is False
    assert "num_dias_agenda" in form.errors
    assert "multa_percent" in form.errors
    assert "mora_percent_am" in form.errors


@pytest.mark.django_db
def test_admin_form_accepts_br_decimals_and_valor(tenant_a):
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )
    form = ChargeAdminForm(
        data={
            "tenant": tenant_a.id,
            "idempotency_key": "num-ok",
            "customer": customer.id,
            "valor_reais": "6,00",
            "due_date": "2026-08-01",
            "charge_kind": Charge.ChargeKind.SIMPLE,
            "billing_type": "BOLETO",
            "description": "",
            "seu_numero": "T001",
            "num_dias_agenda": "15",
            "multa_percent": "2,50",
            "mora_percent_am": "1",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["amount_cents"] == 600
    assert form.cleaned_data["num_dias_agenda"] == 15
    assert form.cleaned_data["multa_percent"] == Decimal("2.50")
    assert form.cleaned_data["mora_percent_am"] == Decimal("1")


@pytest.mark.django_db
def test_admin_form_rejects_past_due_date(tenant_a, settings):
    settings.TIME_ZONE = "America/Sao_Paulo"
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )
    past = (timezone.localdate() - timedelta(days=1)).isoformat()
    form = ChargeAdminForm(
        data={
            "tenant": tenant_a.id,
            "idempotency_key": "due-past",
            "customer": customer.id,
            "valor_reais": "6,00",
            "due_date": past,
            "charge_kind": Charge.ChargeKind.SIMPLE,
            "billing_type": "BOLETO",
            "description": "",
            "seu_numero": "T001",
        }
    )
    assert form.is_valid() is False
    assert "due_date" in form.errors


@pytest.mark.django_db
def test_create_charge_rejects_past_due(tenant_a, settings):
    settings.TIME_ZONE = "America/Sao_Paulo"
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )
    with pytest.raises(InvalidChargeInputError, match="anterior|16:00"):
        create_charge(
            tenant=tenant_a,
            idempotency_key="due-api",
            customer=customer,
            amount_cents=600,
            due_date=timezone.localdate() - timedelta(days=1),
            seu_numero="T002",
        )
