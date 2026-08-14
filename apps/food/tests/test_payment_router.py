"""EPIC-0/1 — roteamento food_payment_provider e isolamento Mercado Pago."""

from unittest.mock import patch

import pytest

from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.registry import get_food_payment_provider
from apps.food.payments.router import (
    PROVIDER_INTER,
    PROVIDER_MERCADOPAGO,
    resolve_food_payment_provider,
)
from apps.food.payments.services import create_payment_intent_for_order
from apps.food.services import (
    create_food_customer,
    create_food_product,
    create_order,
    mark_order_paid,
)


@pytest.fixture
def food_setup(tenant_a):
    customer = create_food_customer(
        tenant=tenant_a,
        name="Cliente Router",
        phone_e164="+5511999000001",
        document="52998224725",
        email="cliente@example.com",
    )
    product = create_food_product(
        tenant=tenant_a,
        sku="ITEM-R1",
        name="Item Router",
        price_cents=5000,
        initial_stock=1,
    )
    return customer, product


@pytest.mark.django_db
def test_resolve_food_payment_provider_defaults_inter(tenant_a):
    assert resolve_food_payment_provider(tenant=tenant_a) == PROVIDER_INTER


@pytest.mark.django_db
def test_resolve_food_payment_provider_from_settings(tenant_a):
    tenant_a.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant_a.save(update_fields=["settings"])
    assert resolve_food_payment_provider(tenant=tenant_a) == PROVIDER_MERCADOPAGO


@pytest.mark.django_db
def test_mercadopago_does_not_call_create_charge(tenant_a, food_setup, settings):
    customer, product = food_setup
    tenant_a.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant_a.save(update_fields=["settings"])
    settings.PAYMENT_HTTP_MODE = "stub"

    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="router-mp-001",
        await_pix=True,
    )

    with patch("apps.billing.services.create_charge") as mock_charge:
        updated = create_payment_intent_for_order(
            tenant=tenant_a, order_id=order.id, method="pix"
        )
        mock_charge.assert_not_called()

    payment = FoodPayment.objects.get(order=updated, tenant=tenant_a)
    assert payment.provider == PROVIDER_MERCADOPAGO
    assert payment.pix_copy_paste


@pytest.mark.django_db
def test_inter_creates_food_payment_and_charge(
    tenant_a, food_setup, settings
):
    customer, product = food_setup
    settings.PAYMENT_HTTP_MODE = "stub"

    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="router-inter-001",
        await_pix=True,
    )

    updated = create_payment_intent_for_order(
        tenant=tenant_a, order_id=order.id, method="pix"
    )
    assert updated.charge_id is not None
    payment = FoodPayment.objects.get(order=updated, tenant=tenant_a)
    assert payment.provider == PROVIDER_INTER
    assert payment.method == FoodPayment.Method.PIX
    assert payment.charge_id == updated.charge_id


@pytest.mark.django_db
def test_mark_order_paid_idempotent_stock(tenant_a, food_setup):
    customer, product = food_setup
    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="router-paid-001",
        await_pix=True,
    )
    paid = mark_order_paid(tenant=tenant_a, order_id=order.id, provider_ref="REF-1")
    again = mark_order_paid(tenant=tenant_a, order_id=order.id, provider_ref="REF-1")
    assert paid.id == again.id
    assert paid.payment_status == FoodOrder.PaymentStatus.PAID
    product.stock_balance.refresh_from_db()
    assert product.stock_balance.quantity == 0


@pytest.mark.django_db
def test_get_food_payment_provider_kind(tenant_a):
    tenant_a.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant_a.save(update_fields=["settings"])
    provider = get_food_payment_provider(tenant=tenant_a)
    assert provider.kind == PROVIDER_MERCADOPAGO
