from datetime import date
from unittest.mock import MagicMock

import pytest

from apps.billing.exceptions import IncompatiblePaymentError, InvalidChargeInputError
from apps.billing.models import Charge, PaymentEvent
from apps.billing.services import cancel_charge, create_charge, sync_charge_from_gateway
from apps.master_data.services import create_customer
from integrations.payments.port import ChargeRegisterResult


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


@pytest.mark.django_db
def test_cancel_rejects_paid(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="c-paid",
        customer=customer,
        amount_cents=1000,
        due_date=date(2026, 8, 1),
    )
    charge.status = Charge.Status.PAID
    charge.save(update_fields=["status"])
    with pytest.raises(IncompatiblePaymentError, match="paga"):
        cancel_charge(charge)


@pytest.mark.django_db
def test_cancel_rejects_failed(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="c-fail",
        customer=customer,
        amount_cents=1000,
        due_date=date(2026, 8, 1),
    )
    charge.status = Charge.Status.FAILED
    charge.save(update_fields=["status"])
    with pytest.raises(IncompatiblePaymentError, match="falha"):
        cancel_charge(charge)


@pytest.mark.django_db
def test_cancel_idempotent_when_already_cancelled(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="c-canc",
        customer=customer,
        amount_cents=1000,
        due_date=date(2026, 8, 1),
    )
    cancel_charge(charge, motivo_cancelamento="ACERTOS")
    again = cancel_charge(charge, motivo_cancelamento="ACERTOS")
    assert again.status == Charge.Status.CANCELLED


@pytest.mark.django_db
def test_cancel_rejects_invalid_motivo(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="c-mot",
        customer=customer,
        amount_cents=1000,
        due_date=date(2026, 8, 1),
    )
    with pytest.raises(InvalidChargeInputError):
        cancel_charge(charge, motivo_cancelamento="XYZ")


@pytest.mark.django_db
def test_cancel_accepts_inter_motivo(tenant_a, customer):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="c-cli",
        customer=customer,
        amount_cents=1000,
        due_date=date(2026, 8, 1),
    )
    cancel_charge(charge, motivo_cancelamento="CLIENTE_DESISTIU")
    charge.refresh_from_db()
    assert charge.status == Charge.Status.CANCELLED
    assert charge.gateway_payload["motivo_cancelamento"] == "CLIENTE_DESISTIU"


@pytest.mark.django_db
def test_sync_marks_paid_from_gateway(tenant_a, customer, monkeypatch):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="c-sync",
        customer=customer,
        amount_cents=600,
        due_date=date(2026, 7, 27),
    )

    fake = MagicMock()
    fake.kind = "inter"
    fake.consultar_cobranca.return_value = ChargeRegisterResult(
        external_ref=charge.gateway_ref,
        status=Charge.Status.PAID,
        raw={
            "cobranca": {
                "codigoSolicitacao": charge.gateway_ref,
                "situacao": "RECEBIDO",
                "valorNominal": 6.0,
                "valorTotalRecebido": 6.0,
                "dataSituacao": "2026-07-20",
                "boleto": {"linhaDigitavel": "0779", "codigoBarras": "0779"},
            }
        },
        digitable_line="0779",
        barcode="0779",
        extras={
            "situacao": "RECEBIDO",
            "data_situacao": "2026-07-20",
            "received_cents": 600,
            "amount_cents": 600,
            "digitable_line": "0779",
            "barcode": "0779",
        },
    )
    monkeypatch.setattr(
        "apps.billing.services.get_payment_gateway",
        lambda **kwargs: fake,
    )

    sync_charge_from_gateway(charge)
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert charge.digitable_line == "0779"
    assert PaymentEvent.objects.filter(charge=charge).count() == 1
