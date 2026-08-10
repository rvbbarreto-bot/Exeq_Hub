"""Sprint 2 — API pedidos + Pix intent + webhook confirm."""

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from apps.billing.models import Charge, WebhookInbox
from apps.billing.services import ingest_gateway_webhook
from apps.food.models import FoodOrder
from apps.food.services import (
    create_food_customer,
    create_food_product,
    create_order,
    create_pix_intent_for_order,
)


def _sign(payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(
        settings.WEBHOOK_GATEWAY_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return body, signature


@pytest.fixture
def food_customer(tenant_a):
    return create_food_customer(
        tenant=tenant_a,
        name="Cliente Food API",
        phone_e164="+5511988887777",
        document="52998224725",
    )


@pytest.fixture
def food_product(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="BOLO-01",
        name="Bolo kg",
        price_cents=5000,
        cost_cents=2000,
        unit="kg",
        initial_stock=Decimal("20"),
    )


@pytest.mark.django_db
def test_api_create_list_order_and_pix(
    api_client, auth_header, food_customer, food_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    create = api_client.post(
        "/api/v1/food/orders/",
        {
            "customer_id": str(food_customer.id),
            "channel": "whatsapp",
            "lines": [{"product_id": str(food_product.id), "quantity": "1"}],
            "idempotency_key": "api-food-order-001",
            "await_pix": True,
            "request_pix": False,
        },
        format="json",
        **auth_header,
    )
    assert create.status_code == 201, create.content
    order_id = create.data["id"]
    assert create.data["payment_status"] == "awaiting_pix"
    assert create.data["channel"] == "whatsapp"
    assert create.data["total_cents"] == 5000

    listed = api_client.get("/api/v1/food/orders/", **auth_header)
    assert listed.status_code == 200
    assert listed.data["count"] >= 1

    pix = api_client.post(
        f"/api/v1/food/orders/{order_id}/pix/",
        {},
        format="json",
        **auth_header,
    )
    assert pix.status_code == 200, pix.content
    assert pix.data["charge_id"]
    assert pix.data["payment_status"] == "awaiting_pix"
    # stub geralmente preenche pix_copy_paste
    order = FoodOrder.objects.get(pk=order_id)
    assert order.charge_id is not None
    assert order.charge.status in {
        Charge.Status.REGISTERED,
        Charge.Status.PENDING,
        Charge.Status.PAID,
    }


@pytest.mark.django_db
def test_api_create_with_request_pix(
    api_client, auth_header, food_customer, food_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    create = api_client.post(
        "/api/v1/food/orders/",
        {
            "customer_id": str(food_customer.id),
            "channel": "counter",
            "lines": [{"product_id": str(food_product.id), "quantity": "1"}],
            "idempotency_key": "api-food-order-pix-inline",
            "request_pix": True,
        },
        format="json",
        **auth_header,
    )
    assert create.status_code == 201, create.content
    assert create.data["charge_id"]


@pytest.mark.django_db
def test_webhook_pays_linked_food_order(
    tenant_a, food_customer, food_product, settings
):
    settings.PAYMENT_HTTP_MODE = "stub"
    order = create_order(
        tenant=tenant_a,
        customer_id=food_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": food_product.id, "quantity": "1"}],
        idempotency_key="food-wh-001",
        await_pix=True,
    )
    order = create_pix_intent_for_order(tenant=tenant_a, order_id=order.id)
    charge = order.charge
    assert charge is not None

    payload = {
        "cobranca": {
            "codigoSolicitacao": charge.gateway_ref,
            "situacao": "RECEBIDO",
            "valorNominal": 50.0,
            "valorTotalRecebido": 50.0,
            "dataSituacao": timezone.now().isoformat(),
            "seuNumero": charge.seu_numero or "X",
        }
    }
    body, signature = _sign(payload)
    inbox = ingest_gateway_webhook(raw_body=body, signature=signature, payload=payload)
    assert inbox.status == WebhookInbox.Status.PROCESSED
    order.refresh_from_db()
    charge.refresh_from_db()
    assert charge.status == Charge.Status.PAID
    assert order.payment_status == FoodOrder.PaymentStatus.PAID
    assert order.status == FoodOrder.Status.CONFIRMED
    food_product.stock_balance.refresh_from_db()
    assert food_product.stock_balance.quantity == Decimal("19")


@pytest.mark.django_db
def test_api_products_and_customers(api_client, auth_header, tenant_a):
    cust = api_client.post(
        "/api/v1/food/customers/",
        {"name": "Ana", "phone_e164": "+5511911112222", "document": "52998224725"},
        format="json",
        **auth_header,
    )
    assert cust.status_code == 201, cust.content
    prod = api_client.post(
        "/api/v1/food/products/",
        {
            "sku": "SUCO-01",
            "name": "Suco",
            "price_cents": 800,
            "initial_stock": "50",
        },
        format="json",
        **auth_header,
    )
    assert prod.status_code == 201, prod.content
