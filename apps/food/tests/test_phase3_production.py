"""Fase 3 — BOM, produção, reserva e MRP lite."""

from datetime import date, time
from decimal import Decimal

import pytest

from apps.food.exceptions import FoodInsufficientStockError
from apps.food.models import FoodProductionOrder, FoodStockBalance
from apps.food.production import (
    complete_production,
    create_bom,
    create_capacity_slot,
    create_production_order,
    mrp_suggestions,
    start_production,
)
from apps.food.services import (
    create_food_product,
    release_stock_reservation,
    reserve_stock,
)


@pytest.fixture
def flour(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="INS-FAR",
        name="Farinha",
        price_cents=100,
        cost_cents=50,
        unit="kg",
        initial_stock=Decimal("100"),
    )


@pytest.fixture
def bread(tenant_a):
    p = create_food_product(
        tenant=tenant_a,
        sku="PA-FRA",
        name="Pão francês",
        price_cents=1200,
        cost_cents=400,
        unit="un",
        initial_stock=Decimal("0"),
        min_quantity=Decimal("20"),
    )
    return p


@pytest.mark.django_db
def test_reserve_and_available(tenant_a, flour):
    bal = reserve_stock(
        tenant=tenant_a, product=flour, quantity=Decimal("30"), reason="op"
    )
    assert bal.reserved_quantity == Decimal("30")
    assert bal.available_quantity == Decimal("70")
    with pytest.raises(FoodInsufficientStockError):
        reserve_stock(tenant=tenant_a, product=flour, quantity=Decimal("80"))
    release_stock_reservation(tenant=tenant_a, product=flour, quantity=Decimal("10"))
    flour.stock_balance.refresh_from_db()
    assert flour.stock_balance.reserved_quantity == Decimal("20")


@pytest.mark.django_db
def test_production_bom_yield_and_mrp(tenant_a, flour, bread):
    bom = create_bom(
        tenant=tenant_a,
        product_id=bread.id,
        name="Receita pão",
        expected_yield_bps=9000,  # 90%
        components=[
            {
                "product_id": flour.id,
                "quantity_per_unit": "0.050",  # 50g farinha / un
                "scrap_bps": 0,
            }
        ],
    )
    slot = create_capacity_slot(
        tenant=tenant_a,
        service_date=date.today(),
        starts_at=time(6, 0),
        ends_at=time(12, 0),
        capacity_units=100,
        name="Manhã",
    )
    op = create_production_order(
        tenant=tenant_a,
        product_id=bread.id,
        quantity_planned=Decimal("100"),
        idempotency_key="op-pao-1",
        capacity_slot_id=slot.id,
    )
    assert op.status == FoodProductionOrder.Status.PLANNED
    slot.refresh_from_db()
    assert slot.booked_units == 100

    op = start_production(tenant=tenant_a, production_order_id=op.id)
    assert op.status == FoodProductionOrder.Status.IN_PROGRESS
    flour.stock_balance.refresh_from_db()
    # 100 * 0.05 = 5 kg consumidos
    assert flour.stock_balance.quantity == Decimal("95")

    op = complete_production(tenant=tenant_a, production_order_id=op.id)
    assert op.status == FoodProductionOrder.Status.DONE
    assert op.quantity_produced == Decimal("90.000")  # 90% yield
    assert op.loss_quantity == Decimal("10.000")
    bread.stock_balance.refresh_from_db()
    assert bread.stock_balance.quantity == Decimal("90.000")

    # pão ainda abaixo do min 20? min was 20, available 90 > 20, no suggestion for shortage min
    # force min high
    FoodStockBalance.objects.filter(product=bread).update(min_quantity=Decimal("200"))
    suggestions = mrp_suggestions(tenant=tenant_a)
    skus = {s["sku"] for s in suggestions}
    assert "PA-FRA" in skus


@pytest.mark.django_db
def test_api_bom_and_production(api_client, auth_header, tenant_a, flour, bread):
    bom = api_client.post(
        "/api/v1/food/boms/",
        {
            "product_id": str(bread.id),
            "name": "BOM API",
            "expected_yield_bps": 10000,
            "components": [
                {"product_id": str(flour.id), "quantity_per_unit": "0.1"},
            ],
        },
        format="json",
        **auth_header,
    )
    assert bom.status_code == 201, bom.content
    op = api_client.post(
        "/api/v1/food/production-orders/",
        {
            "product_id": str(bread.id),
            "quantity_planned": "10",
            "idempotency_key": "api-op-1",
        },
        format="json",
        **auth_header,
    )
    assert op.status_code == 201, op.content
    start = api_client.post(
        f"/api/v1/food/production-orders/{op.data['id']}/start/",
        {},
        format="json",
        **auth_header,
    )
    assert start.status_code == 200, start.content
    done = api_client.post(
        f"/api/v1/food/production-orders/{op.data['id']}/complete/",
        {},
        format="json",
        **auth_header,
    )
    assert done.status_code == 200
    assert done.data["status"] == "done"
    mrp = api_client.get("/api/v1/food/mrp", **auth_header)
    assert mrp.status_code == 200
    assert "suggestions" in mrp.data
