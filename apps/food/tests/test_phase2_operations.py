"""Fase 2 — compras, delivery, marketplace unificado."""

from datetime import date
from decimal import Decimal

import pytest

from apps.food.models import FoodOrder, FoodPurchase, FoodStockBalance
from apps.food.operations import (
    assign_order_to_route,
    create_delivery_route,
    create_purchase,
    create_supplier,
    import_marketplace_order,
    receive_purchase,
    transition_order_status,
    update_delivery_stop_status,
)
from apps.food.services import create_food_customer, create_food_product, create_order


@pytest.fixture
def product(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="FAR-01",
        name="Farinha",
        price_cents=1500,
        cost_cents=800,
        unit="kg",
        initial_stock=Decimal("5"),
    )


@pytest.fixture
def customer(tenant_a):
    return create_food_customer(
        tenant=tenant_a,
        name="Cliente Ops",
        phone_e164="+5511966665555",
    )


@pytest.mark.django_db
def test_purchase_receive_stock_in(tenant_a, product):
    supplier = create_supplier(
        tenant=tenant_a, name="Moinho XYZ", document="11222333000181"
    )
    purchase = create_purchase(
        tenant=tenant_a,
        supplier_id=supplier.id,
        lines=[
            {
                "product_id": product.id,
                "quantity": "10",
                "unit_cost_cents": 700,
            }
        ],
        idempotency_key="purchase-001",
    )
    assert purchase.status == FoodPurchase.Status.ORDERED
    assert purchase.total_cents == 7000
    receive_purchase(tenant=tenant_a, purchase_id=purchase.id)
    purchase.refresh_from_db()
    assert purchase.status == FoodPurchase.Status.RECEIVED
    bal = FoodStockBalance.objects.get(product=product)
    assert bal.quantity == Decimal("15")
    product.refresh_from_db()
    assert product.cost_cents == 700
    # idempotente
    receive_purchase(tenant=tenant_a, purchase_id=purchase.id)
    bal.refresh_from_db()
    assert bal.quantity == Decimal("15")


@pytest.mark.django_db
def test_order_kitchen_and_delivery_route(tenant_a, product, customer):
    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="ops-order-1",
        await_pix=False,
    )
    assert order.status == FoodOrder.Status.CONFIRMED
    order = transition_order_status(
        tenant=tenant_a, order_id=order.id, to_status=FoodOrder.Status.PREPARING
    )
    order = transition_order_status(
        tenant=tenant_a, order_id=order.id, to_status=FoodOrder.Status.READY
    )

    route = create_delivery_route(
        tenant=tenant_a,
        name="Zona Sul",
        service_date=date.today(),
        driver_name="João",
    )
    stop = assign_order_to_route(
        tenant=tenant_a, route_id=route.id, order_id=order.id
    )
    assert stop.sequence == 1
    order.refresh_from_db()
    assert order.fulfillment_mode == FoodOrder.FulfillmentMode.DELIVERY

    stop = update_delivery_stop_status(
        tenant=tenant_a, stop_id=stop.id, to_status="out_for_delivery"
    )
    stop = update_delivery_stop_status(
        tenant=tenant_a, stop_id=stop.id, to_status="delivered"
    )
    order.refresh_from_db()
    assert order.status == FoodOrder.Status.FULFILLED
    assert stop.status == "delivered"


@pytest.mark.django_db
def test_marketplace_import_unified_order(tenant_a, product):
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="IFO-999",
        customer_name="Cliente iFood",
        customer_phone="+5511955554444",
        lines=[{"sku": "FAR-01", "quantity": "2", "unit_price_cents": 1500}],
        total_cents=3000,
        delivery_address="Rua A, 100",
        merchant_ref="loja-1",
        paid=True,
    )
    assert order.channel == FoodOrder.Channel.IFOOD
    assert order.channel_ref == "IFO-999"
    assert order.payment_status == FoodOrder.PaymentStatus.PAID
    assert order.fulfillment_mode == FoodOrder.FulfillmentMode.DELIVERY
    assert order.marketplace_connection_id is not None
    assert order.status == FoodOrder.Status.PREPARING
    again = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="IFO-999",
        customer_name="Cliente iFood",
        lines=[{"sku": "FAR-01", "quantity": "2"}],
        paid=True,
    )
    assert again.id == order.id


@pytest.mark.django_db
def test_api_phase2_purchase_and_import(
    api_client, auth_header, tenant_a, product, customer
):
    sup = api_client.post(
        "/api/v1/food/suppliers/",
        {"name": "Fornecedor API", "document": "11222333000181"},
        format="json",
        **auth_header,
    )
    assert sup.status_code == 201, sup.content
    purchase = api_client.post(
        "/api/v1/food/purchases/",
        {
            "supplier_id": sup.data["id"],
            "idempotency_key": "api-purch-1",
            "lines": [{"product_id": str(product.id), "quantity": "3", "unit_cost_cents": 500}],
        },
        format="json",
        **auth_header,
    )
    assert purchase.status_code == 201, purchase.content
    recv = api_client.post(
        f"/api/v1/food/purchases/{purchase.data['id']}/receive/",
        {},
        format="json",
        **auth_header,
    )
    assert recv.status_code == 200
    assert recv.data["status"] == "received"

    mp = api_client.post(
        "/api/v1/food/marketplace/import",
        {
            "provider": "aiqfome",
            "external_order_id": "AQ-1",
            "customer_name": "Aq",
            "customer_phone": "+5511944443333",
            "lines": [{"sku": product.sku, "quantity": "1", "unit_price_cents": 1500}],
            "merchant_ref": "aq-loja",
        },
        format="json",
        **auth_header,
    )
    assert mp.status_code == 201, mp.content
    assert mp.data["channel"] == "aiqfome"
