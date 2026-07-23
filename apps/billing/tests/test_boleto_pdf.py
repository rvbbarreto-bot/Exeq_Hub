"""PDF Inter → StoredFile + download API."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.urls import reverse
from django.test import Client

from apps.accounts.models import User
from apps.billing.due_date_rules import min_due_date
from apps.billing.services import create_charge, ensure_charge_pdf
from apps.master_data.services import create_customer
from apps.ops.models import StoredFile
from integrations.payments.banks import InterPaymentGateway
from shared.storage import get_storage


def _due():
    return min_due_date() + timedelta(days=7)


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


@pytest.mark.django_db
def test_stub_baixar_pdf_is_valid_pdf():
    gw = InterPaymentGateway(mode="stub", token="")
    data = gw.baixar_pdf(ref="inter_abc")
    assert data.startswith(b"%PDF")


@pytest.mark.django_db
def test_ensure_charge_pdf_persists_stored_file(tenant_a, customer, settings, tmp_path):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="pdf-stub-1",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    assert charge.pdf_file_id
    stored = charge.pdf_file
    assert stored.purpose == "boleto_pdf"
    data = get_storage().get(key=stored.object_key)
    assert data.startswith(b"%PDF")
    assert StoredFile.objects.filter(purpose="boleto_pdf").count() == 1

    # idempotente
    again = ensure_charge_pdf(charge)
    assert again.pdf_file_id == charge.pdf_file_id
    assert StoredFile.objects.filter(purpose="boleto_pdf").count() == 1


@pytest.mark.django_db
def test_ensure_charge_pdf_http_path(tenant_a, customer, monkeypatch, settings, tmp_path):
    settings.PAYMENT_HTTP_MODE = "http"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)

    fake = MagicMock()
    fake.kind = "inter"
    fake.registrar_cobranca.return_value = __import__(
        "integrations.payments.port", fromlist=["ChargeRegisterResult"]
    ).ChargeRegisterResult(
        external_ref="sol-pdf",
        status="registered",
        raw={"codigoSolicitacao": "sol-pdf"},
        digitable_line="23793",
        barcode="2379",
    )
    fake.baixar_pdf.return_value = b"%PDF-1.4\nstub\n%%EOF\n"
    monkeypatch.setattr(
        "apps.billing.services.get_payment_gateway",
        lambda **kwargs: fake,
    )

    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="pdf-http-1",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    assert fake.baixar_pdf.called
    charge.refresh_from_db()
    assert charge.pdf_file_id
    assert charge.pdf_file.purpose == "boleto_pdf"


@pytest.mark.django_db
def test_charges_pdf_api(api_client, auth_header, tenant_a, customer, settings, tmp_path):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="pdf-api-1",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    res = api_client.get(f"/api/v1/charges/{charge.id}/pdf/", **auth_header)
    assert res.status_code == 200
    assert res["Content-Type"].startswith("application/pdf")
    body = b"".join(res.streaming_content) if hasattr(res, "streaming_content") else res.content
    assert body.startswith(b"%PDF")

    detail = api_client.get(f"/api/v1/charges/{charge.id}/", **auth_header)
    assert detail.status_code == 200
    assert detail.data["has_boleto_pdf"] is True


@pytest.mark.django_db
def test_admin_charge_pdf_download(tenant_a, customer, settings, tmp_path):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    User.objects.create_superuser(
        email="po-pdf@exeq.local",
        password="Secret123!",
        name="PO",
    )
    client = Client()
    assert client.login(email="po-pdf@exeq.local", password="Secret123!")
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="pdf-admin-1",
        customer=customer,
        amount_cents=5000,
        due_date=_due(),
    )
    url = reverse("admin:billing_charge_pdf", args=[charge.pk])
    res = client.get(url)
    assert res.status_code == 200
    assert res["Content-Type"].startswith("application/pdf")
