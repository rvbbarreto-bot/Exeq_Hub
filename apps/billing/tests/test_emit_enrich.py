from datetime import date
from unittest.mock import MagicMock

import pytest

from apps.billing.models import Charge
from apps.billing.services import create_charge, sync_charge_from_gateway
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
def test_create_charge_stub_persists_digitable_line(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="enrich-stub",
        customer=customer,
        amount_cents=600,
        due_date=date(2026, 8, 15),
    )
    assert charge.status == Charge.Status.REGISTERED
    assert charge.gateway_ref
    assert charge.digitable_line
    assert charge.barcode


@pytest.mark.django_db
def test_create_charge_enriches_via_consultar_when_post_empty(
    tenant_a, customer, monkeypatch, settings
):
    settings.PAYMENT_HTTP_MODE = "http"

    fake = MagicMock()
    fake.kind = "inter"
    fake.registrar_cobranca.return_value = ChargeRegisterResult(
        external_ref="inter-ref-1",
        status="registered",
        raw={"codigoSolicitacao": "inter-ref-1"},
    )
    fake.consultar_cobranca.return_value = ChargeRegisterResult(
        external_ref="inter-ref-1",
        status="registered",
        raw={"cobranca": {"situacao": "A_RECEBER"}},
        digitable_line="23793.38128 60000.000003 00000.000400 1 00000000000001",
        barcode="23791000000000000000000000000000000000000000",
        pix_copy_paste="00020126PIX",
        extras={"situacao": "A_RECEBER"},
    )
    fake.baixar_pdf.return_value = b"%PDF-1.4\nstub\n%%EOF\n"
    monkeypatch.setattr(
        "apps.billing.services.get_payment_gateway",
        lambda **kwargs: fake,
    )
    monkeypatch.setattr("apps.billing.services.time.sleep", lambda *_a, **_k: None)

    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="enrich-http",
        customer=customer,
        amount_cents=600,
        due_date=date(2026, 8, 15),
    )
    assert charge.gateway_ref == "inter-ref-1"
    assert charge.digitable_line.startswith("23793")
    assert charge.pix_copy_paste == "00020126PIX"
    assert fake.consultar_cobranca.called


@pytest.mark.django_db
def test_sync_still_marks_paid(tenant_a, customer, monkeypatch):
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="enrich-sync-paid",
        customer=customer,
        amount_cents=600,
        due_date=date(2026, 8, 15),
    )
    fake = MagicMock()
    fake.kind = "inter"
    fake.consultar_cobranca.return_value = ChargeRegisterResult(
        external_ref=charge.gateway_ref,
        status=Charge.Status.PAID,
        raw={},
        digitable_line="0779",
        barcode="0779",
        extras={
            "situacao": "RECEBIDO",
            "data_situacao": "2026-07-20",
            "received_cents": 600,
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
