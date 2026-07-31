"""D10 — Admin bulk cancel com motivo Inter selecionável."""

from datetime import timedelta

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.billing.admin import ChargeAdmin
from apps.billing.due_date_rules import min_due_date
from apps.billing.models import Charge
from apps.billing.services import create_charge
from apps.master_data.services import create_customer


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador Admin",
    )


def _admin_request(path="/admin/billing/charge/", data=None):
    User = get_user_model()
    user = User.objects.create_superuser(
        email="qa-billing-admin@exeq.local",
        password="Secret123!",
        name="QA Billing",
    )
    factory = RequestFactory()
    if data is None:
        request = factory.get(path)
    else:
        request = factory.post(path, data)
    request.user = user
    setattr(request, "session", "session")
    messages = FallbackStorage(request)
    setattr(request, "_messages", messages)
    return request


@pytest.mark.django_db
def test_admin_bulk_cancel_shows_motivo_form(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="adm-cancel-form",
        customer=customer,
        amount_cents=5000,
        due_date=min_due_date() + timedelta(days=3),
    )
    site = AdminSite()
    model_admin = ChargeAdmin(Charge, site)
    request = _admin_request()
    response = model_admin.cancelar_cobrancas(
        request, Charge.objects.filter(id=charge.id)
    )
    assert response is not None
    assert response.status_code == 200
    content = response.rendered_content
    assert "motivo_cancelamento" in content
    assert "APEDIDODOCLIENTE" in content
    assert "ACERTOS" in content


@pytest.mark.django_db
def test_admin_bulk_cancel_applies_selected_motivo(tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    charge = create_charge(
        tenant=tenant_a,
        idempotency_key="adm-cancel-apply",
        customer=customer,
        amount_cents=5000,
        due_date=min_due_date() + timedelta(days=3),
    )
    site = AdminSite()
    model_admin = ChargeAdmin(Charge, site)
    request = _admin_request(
        data={
            "action": "cancelar_cobrancas",
            "apply": "1",
            "motivo_cancelamento": "APEDIDODOCLIENTE",
            ACTION_CHECKBOX_NAME: str(charge.id),
        }
    )
    result = model_admin.cancelar_cobrancas(
        request, Charge.objects.filter(id=charge.id)
    )
    assert result is None
    charge.refresh_from_db()
    assert charge.status == Charge.Status.CANCELLED
    assert (charge.gateway_payload or {}).get("motivo_cancelamento") == "APEDIDODOCLIENTE"
