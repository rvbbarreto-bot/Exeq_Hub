"""EPIC-2 — Mercado Pago Pix (Food)."""

from unittest.mock import patch

import pytest

from apps.food.exceptions import FoodPaymentEmailRequiredError
from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.mercadopago.client import MercadoPagoClient
from apps.food.payments.mercadopago.payer import split_payer_name
from apps.food.payments.router import PROVIDER_MERCADOPAGO
from apps.food.payments.services import create_payment_intent_for_order
from apps.food.services import (
    create_food_customer,
    create_food_product,
    create_order,
)


@pytest.fixture
def mp_tenant(tenant_a):
    tenant_a.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant_a.save(update_fields=["settings"])
    return tenant_a


@pytest.fixture
def mp_customer(mp_tenant):
    return create_food_customer(
        tenant=mp_tenant,
        name="Maria Silva",
        phone_e164="+5511988880001",
        document="52998224725",
        email="maria@example.com",
    )


@pytest.fixture
def mp_product(mp_tenant):
    return create_food_product(
        tenant=mp_tenant,
        sku="MP-PIX-01",
        name="Produto MP",
        price_cents=5000,
        initial_stock=10,
    )


@pytest.mark.django_db
def test_mp_pix_stub_creates_food_payment(mp_tenant, mp_customer, mp_product, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    order = create_order(
        tenant=mp_tenant,
        customer_id=mp_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": mp_product.id, "quantity": "1"}],
        idempotency_key="mp-pix-001",
        await_pix=True,
    )
    with patch("apps.billing.services.create_charge") as mock_charge:
        updated = create_payment_intent_for_order(
            tenant=mp_tenant, order_id=order.id, method="pix"
        )
        mock_charge.assert_not_called()

    assert updated.payment_status == FoodOrder.PaymentStatus.AWAITING_PAYMENT
    assert updated.charge_id is None
    payment = FoodPayment.objects.get(order=updated, tenant=mp_tenant)
    assert payment.provider == PROVIDER_MERCADOPAGO
    assert payment.method == FoodPayment.Method.PIX
    assert payment.pix_copy_paste.startswith("000201")
    assert payment.provider_payment_id.startswith("mp_stub_")


@pytest.mark.django_db
def test_mp_pix_email_required(mp_tenant, mp_product, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    customer = create_food_customer(
        tenant=mp_tenant,
        name="Sem Email",
        document="52998224725",
        email="",
    )
    order = create_order(
        tenant=mp_tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": mp_product.id, "quantity": "1"}],
        idempotency_key="mp-pix-no-email",
        await_pix=True,
    )
    with pytest.raises(FoodPaymentEmailRequiredError):
        create_payment_intent_for_order(
            tenant=mp_tenant, order_id=order.id, method="pix"
        )


@pytest.mark.django_db
def test_mp_pix_idempotent_intent(mp_tenant, mp_customer, mp_product, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    order = create_order(
        tenant=mp_tenant,
        customer_id=mp_customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": mp_product.id, "quantity": "1"}],
        idempotency_key="mp-pix-idem",
        await_pix=True,
    )
    first = create_payment_intent_for_order(
        tenant=mp_tenant, order_id=order.id, method="pix"
    )
    with patch.object(MercadoPagoClient, "create_pix_payment") as mock_create:
        second = create_payment_intent_for_order(
            tenant=mp_tenant, order_id=order.id, method="pix"
        )
        mock_create.assert_not_called()
    assert first.id == second.id
    assert FoodPayment.objects.filter(order=order, tenant=mp_tenant).count() == 1


@pytest.mark.django_db
def test_mp_pix_api_request_payment(
    api_client, auth_header, mp_tenant, mp_customer, mp_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    mp_tenant.settings = {
        "food_payment_provider": PROVIDER_MERCADOPAGO,
    }
    mp_tenant.save(update_fields=["settings"])

    response = api_client.post(
        "/api/v1/food/orders/",
        {
            "customer_id": str(mp_customer.id),
            "channel": "whatsapp",
            "lines": [{"product_id": str(mp_product.id), "quantity": "1"}],
            "idempotency_key": "mp-api-request-payment",
            "request_payment": True,
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 201, response.content
    assert response.data["payment_status"] == "awaiting_payment"
    assert response.data["payment"]["provider"] == PROVIDER_MERCADOPAGO
    assert response.data["pix_copy_paste"].startswith("000201")
    assert response.data["charge_id"] is None


def test_split_payer_name():
    assert split_payer_name("Maria") == ("Maria", ".")
    assert split_payer_name("Maria Silva") == ("Maria", "Silva")
