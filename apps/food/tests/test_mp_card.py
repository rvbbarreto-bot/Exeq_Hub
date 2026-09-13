"""EPIC-5 — Mercado Pago cartão (Checkout Transparente)."""

import pytest

from apps.food.exceptions import FoodPaymentCardTokenRequiredError
from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.router import PROVIDER_MERCADOPAGO
from apps.food.payments.services import create_payment_intent_for_order
from apps.food.services import create_food_customer, create_food_product, create_order


@pytest.fixture
def mp_card_setup(tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    tenant_a.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant_a.save(update_fields=["settings"])
    customer = create_food_customer(
        tenant=tenant_a,
        name="Cartao Cliente",
        document="52998224725",
        email="card@example.com",
    )
    product = create_food_product(
        tenant=tenant_a,
        sku="CARD-01",
        name="Produto Card",
        price_cents=5000,
        initial_stock=5,
    )
    return tenant_a, customer, product


@pytest.mark.django_db
def test_mp_card_stub_approves_order(mp_card_setup):
    tenant, customer, product = mp_card_setup
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="mp-card-001",
        await_pix=True,
    )
    updated = create_payment_intent_for_order(
        tenant=tenant,
        order_id=order.id,
        method="card",
        card_token="stub_card_token",
        payment_method_id="visa",
    )
    assert updated.payment_status == FoodOrder.PaymentStatus.PAID
    assert updated.status == FoodOrder.Status.CONFIRMED
    payment = FoodPayment.objects.get(order=updated, tenant=tenant)
    assert payment.method == FoodPayment.Method.CARD
    assert payment.status == FoodPayment.Status.PAID
    assert "token" not in (payment.gateway_payload or {})


@pytest.mark.django_db
def test_mp_card_requires_token(mp_card_setup):
    tenant, customer, product = mp_card_setup
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="mp-card-no-token",
        await_pix=True,
    )
    with pytest.raises(FoodPaymentCardTokenRequiredError):
        create_payment_intent_for_order(
            tenant=tenant,
            order_id=order.id,
            method="card",
            card_token="",
            payment_method_id="visa",
        )


@pytest.mark.django_db
def test_mp_card_api_payment_intent(
    api_client, auth_header, mp_card_setup
):
    tenant, customer, product = mp_card_setup
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="mp-card-api",
        await_pix=True,
    )
    response = api_client.post(
        f"/api/v1/food/orders/{order.id}/payment-intent/",
        {
            "method": "card",
            "token": "stub_card_token",
            "payment_method_id": "visa",
            "installments": 1,
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 200, response.content
    assert response.data["payment_status"] == "paid"
    assert response.data["payment"]["method"] == "card"
