"""EPIC-6 — Contrato WhatsApp / auto-emissão via API."""

from decimal import Decimal

import pytest

from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.router import PROVIDER_MERCADOPAGO
from apps.food.payments.services import (
    create_order_with_auto_payment,
    create_payment_intent_for_order,
)
from apps.food.payments.whatsapp import (
    WHATSAPP_MESSAGE_MAX,
    build_whatsapp_order_paid_message,
    build_whatsapp_payment_message,
    format_brl_cents,
    whatsapp_payment_payload,
)
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
def wa_customer(mp_tenant):
    return create_food_customer(
        tenant=mp_tenant,
        name="Maria Silva",
        phone_e164="+5511988880001",
        document="52998224725",
        email="maria@example.com",
    )


@pytest.fixture
def wa_product(mp_tenant):
    return create_food_product(
        tenant=mp_tenant,
        sku="WA-01",
        name="Item WhatsApp",
        price_cents=5000,
        initial_stock=10,
    )


@pytest.mark.django_db
def test_ca_6_1_api_whatsapp_request_payment_returns_message(
    api_client, auth_header, mp_tenant, wa_customer, wa_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    response = api_client.post(
        "/api/v1/food/orders/",
        {
            "customer_id": str(wa_customer.id),
            "channel": "whatsapp",
            "channel_ref": "wamid.test-001",
            "lines": [{"product_id": str(wa_product.id), "quantity": "1"}],
            "idempotency_key": "wa-api-epic6-001",
            "request_payment": True,
            "payment_method": "pix",
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 201, response.content
    data = response.data
    assert data["channel"] == "whatsapp"
    assert data["channel_ref"] == "wamid.test-001"
    assert data["pix_copy_paste"].startswith("000201")

    wp = data["whatsapp_payment"]
    assert wp is not None
    assert wp["ready"] is True
    assert wp["pix_copy_paste"] == data["pix_copy_paste"]
    assert "Pix Copia e Cola" in wp["message"]
    assert "Maria Silva" in wp["message"]
    assert format_brl_cents(5000) in wp["message"]
    assert len(wp["message"]) <= WHATSAPP_MESSAGE_MAX

    order = FoodOrder.objects.get(pk=data["id"])
    assert FoodPayment.objects.filter(order=order, tenant=mp_tenant).exists()


@pytest.mark.django_db
def test_ca_6_2_non_whatsapp_channel_has_no_whatsapp_payment(
    api_client, auth_header, mp_tenant, wa_customer, wa_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    response = api_client.post(
        "/api/v1/food/orders/",
        {
            "customer_id": str(wa_customer.id),
            "channel": "counter",
            "lines": [{"product_id": str(wa_product.id), "quantity": "1"}],
            "idempotency_key": "wa-api-counter-001",
            "request_payment": True,
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 201, response.content
    assert response.data["whatsapp_payment"] is None


@pytest.mark.django_db
def test_whatsapp_rejects_card_on_create(api_client, auth_header, wa_customer, wa_product):
    response = api_client.post(
        "/api/v1/food/orders/",
        {
            "customer_id": str(wa_customer.id),
            "channel": "whatsapp",
            "lines": [{"product_id": str(wa_product.id), "quantity": "1"}],
            "idempotency_key": "wa-api-card-reject",
            "request_payment": True,
            "payment_method": "card",
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 400, response.content
    assert "payment_method" in response.data


@pytest.mark.django_db
def test_build_whatsapp_payment_message_mp_stub(
    mp_tenant, wa_customer, wa_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    order = create_order(
        tenant=mp_tenant,
        customer_id=wa_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": wa_product.id, "quantity": "1"}],
        idempotency_key="wa-msg-build-001",
        await_pix=True,
    )
    order = create_payment_intent_for_order(
        tenant=mp_tenant, order_id=order.id, method="pix"
    )
    order = FoodOrder.objects.select_related("customer").get(pk=order.id)

    message = build_whatsapp_payment_message(order)
    assert "Maria Silva" in message
    assert "000201" in message
    payload = whatsapp_payment_payload(order)
    assert payload["ready"] is True
    assert payload["message"] == message


@pytest.mark.django_db
def test_build_whatsapp_payment_message_without_pix(mp_tenant, wa_customer, wa_product):
    order = create_order(
        tenant=mp_tenant,
        customer_id=wa_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": wa_product.id, "quantity": "1"}],
        idempotency_key="wa-msg-no-pix",
        await_pix=True,
    )
    order = FoodOrder.objects.select_related("customer").get(pk=order.id)
    message = build_whatsapp_payment_message(order)
    assert "gerando seu Pix" in message
    assert whatsapp_payment_payload(order)["ready"] is False


@pytest.mark.django_db
def test_build_whatsapp_order_paid_message(mp_tenant, wa_customer, wa_product):
    order = create_order(
        tenant=mp_tenant,
        customer_id=wa_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": wa_product.id, "quantity": "1"}],
        idempotency_key="wa-paid-msg",
        await_pix=True,
    )
    order.payment_status = FoodOrder.PaymentStatus.PAID
    order = FoodOrder.objects.select_related("customer").get(pk=order.id)
    message = build_whatsapp_order_paid_message(order)
    assert "Pagamento confirmado" in message
    assert str(order.id)[:8] in message


@pytest.mark.django_db
def test_create_order_with_auto_payment_service(
    mp_tenant, wa_customer, wa_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    order = create_order_with_auto_payment(
        tenant=mp_tenant,
        customer_id=wa_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": wa_product.id, "quantity": Decimal("1")}],
        idempotency_key="wa-service-auto-001",
        payment_method="pix",
        channel_ref="wamid.service-001",
    )
    order = FoodOrder.objects.select_related("customer").get(pk=order.id)
    assert order.channel_ref == "wamid.service-001"
    assert order.payment_status == FoodOrder.PaymentStatus.AWAITING_PAYMENT
    payload = whatsapp_payment_payload(order)
    assert payload["ready"] is True
