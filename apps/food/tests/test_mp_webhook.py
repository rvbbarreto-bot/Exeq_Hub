"""EPIC-3 — webhook Mercado Pago Food."""

import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client

from apps.food.models import FoodOrder, FoodPayment, FoodPaymentEvent
from apps.food.payments.router import PROVIDER_MERCADOPAGO
from apps.food.payments.services import create_payment_intent_for_order
from apps.food.services import create_food_customer, create_food_product, create_order
from apps.food.webhook_views import sign_mercadopago_webhook_test


@pytest.fixture
def mp_client():
    return Client()


@pytest.fixture
def mp_setup(tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.FOOD_MP_WEBHOOK_SECRET = "mp-webhook-test-secret"
    tenant_a.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant_a.save(update_fields=["settings"])
    customer = create_food_customer(
        tenant=tenant_a,
        name="Webhook Cliente",
        document="52998224725",
        email="webhook@example.com",
    )
    product = create_food_product(
        tenant=tenant_a,
        sku="WH-01",
        name="Item WH",
        price_cents=5000,
        initial_stock=Decimal("5"),
    )
    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="mp-wh-order-001",
        await_pix=True,
    )
    order = create_payment_intent_for_order(
        tenant=tenant_a, order_id=order.id, method="pix"
    )
    payment = FoodPayment.objects.get(order=order, tenant=tenant_a)
    return tenant_a, order, payment, product


def _post_webhook(client, *, payment_id: str, settings, request_id: str | None = None):
    request_id = request_id or str(uuid.uuid4())
    payload = {
        "action": "payment.updated",
        "type": "payment",
        "data": {"id": payment_id},
        "id": 999001,
    }
    body = json.dumps(payload).encode()
    signature = sign_mercadopago_webhook_test(
        secret=settings.FOOD_MP_WEBHOOK_SECRET,
        data_id=str(payment_id),
        request_id=request_id,
    )
    return client.post(
        "/api/v1/food/webhooks/mercadopago",
        data=body,
        content_type="application/json",
        HTTP_X_SIGNATURE=signature,
        HTTP_X_REQUEST_ID=request_id,
    )


@pytest.mark.django_db
def test_mp_webhook_approved_pays_order(mp_client, mp_setup, settings):
    tenant_a, order, payment, product = mp_setup
    response = _post_webhook(
        mp_client, payment_id=payment.provider_payment_id, settings=settings
    )
    assert response.status_code == 200, response.content
    order.refresh_from_db()
    payment.refresh_from_db()
    assert payment.status == FoodPayment.Status.PAID
    assert order.payment_status == FoodOrder.PaymentStatus.PAID
    assert order.status == FoodOrder.Status.CONFIRMED
    product.stock_balance.refresh_from_db()
    assert product.stock_balance.quantity == Decimal("4")
    assert FoodPaymentEvent.objects.filter(payment=payment, tenant=tenant_a).count() == 1


@pytest.mark.django_db
def test_mp_webhook_duplicate_idempotent(mp_client, mp_setup, settings):
    tenant_a, order, payment, product = mp_setup
    request_id = str(uuid.uuid4())
    first = _post_webhook(
        mp_client,
        payment_id=payment.provider_payment_id,
        settings=settings,
        request_id=request_id,
    )
    second = _post_webhook(
        mp_client,
        payment_id=payment.provider_payment_id,
        settings=settings,
        request_id=request_id,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    product.stock_balance.refresh_from_db()
    assert product.stock_balance.quantity == Decimal("4")
    assert FoodPaymentEvent.objects.filter(payment=payment, tenant=tenant_a).count() == 1


@pytest.mark.django_db
def test_mp_webhook_invalid_signature(mp_client, mp_setup, settings):
    _tenant, _order, payment, _product = mp_setup
    payload = {"type": "payment", "data": {"id": payment.provider_payment_id}}
    response = mp_client.post(
        "/api/v1/food/webhooks/mercadopago",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_SIGNATURE="ts=1,v1=deadbeef",
        HTTP_X_REQUEST_ID=str(uuid.uuid4()),
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_mp_webhook_payment_not_found(mp_client, settings):
    settings.FOOD_MP_WEBHOOK_SECRET = "mp-webhook-test-secret"
    request_id = str(uuid.uuid4())
    payment_id = "mp_unknown_999"
    signature = sign_mercadopago_webhook_test(
        secret=settings.FOOD_MP_WEBHOOK_SECRET,
        data_id=payment_id,
        request_id=request_id,
    )
    response = mp_client.post(
        "/api/v1/food/webhooks/mercadopago",
        data=json.dumps({"type": "payment", "data": {"id": payment_id}}),
        content_type="application/json",
        HTTP_X_SIGNATURE=signature,
        HTTP_X_REQUEST_ID=request_id,
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_mp_webhook_already_paid_no_double_stock(mp_client, mp_setup, settings):
    tenant_a, order, payment, product = mp_setup
    _post_webhook(mp_client, payment_id=payment.provider_payment_id, settings=settings)
    product.stock_balance.refresh_from_db()
    after_first = product.stock_balance.quantity
    _post_webhook(
        mp_client,
        payment_id=payment.provider_payment_id,
        settings=settings,
        request_id=str(uuid.uuid4()),
    )
    product.stock_balance.refresh_from_db()
    assert product.stock_balance.quantity == after_first
    order.refresh_from_db()
    assert order.payment_status == FoodOrder.PaymentStatus.PAID
