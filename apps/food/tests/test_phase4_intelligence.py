"""Fase 4 — inteligência / previsões."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.food.intelligence import (
    customer_intelligence,
    demand_forecast,
    dynamic_pricing_suggestions,
    intelligence_report,
    production_and_purchase_suggestions,
)
from apps.food.models import FoodOrder
from apps.food.production import create_bom
from apps.food.services import create_food_customer, create_food_product, create_order


@pytest.fixture
def catalog(tenant_a):
    flour = create_food_product(
        tenant=tenant_a,
        sku="F4-FAR",
        name="Farinha F4",
        price_cents=200,
        cost_cents=100,
        unit="kg",
        initial_stock=Decimal("500"),
    )
    bread = create_food_product(
        tenant=tenant_a,
        sku="F4-PAO",
        name="Pão F4",
        price_cents=1000,
        cost_cents=400,
        unit="un",
        initial_stock=Decimal("100"),
        min_quantity=Decimal("150"),
    )
    create_bom(
        tenant=tenant_a,
        product_id=bread.id,
        name="BOM F4",
        components=[{"product_id": flour.id, "quantity_per_unit": "0.05"}],
    )
    customer = create_food_customer(
        tenant=tenant_a,
        name="Cliente F4",
        phone_e164="+5511933332222",
    )
    # histórico de vendas (5 x 10 = 50 un)
    for i in range(5):
        create_order(
            tenant=tenant_a,
            customer_id=customer.id,
            channel=FoodOrder.Channel.COUNTER,
            lines=[{"product_id": bread.id, "quantity": "10"}],
            idempotency_key=f"f4-hist-{i}",
            await_pix=False,
        )
    # deixa estoque residual baixo p/ pricing / MRP
    from apps.food.models import FoodStockBalance

    FoodStockBalance.objects.filter(product=bread).update(
        quantity=Decimal("5"), reserved_quantity=Decimal("0")
    )
    # simula last_order antigo para churn
    customer.refresh_from_db()
    customer.last_order_at = timezone.now() - timedelta(days=45)
    customer.save(update_fields=["last_order_at"])
    return {"flour": flour, "bread": bread, "customer": customer}


@pytest.mark.django_db
def test_demand_forecast_and_suggestions(tenant_a, catalog):
    demand = demand_forecast(tenant=tenant_a, lookback_days=28, horizon_days=7)
    skus = {d["sku"] for d in demand}
    assert "F4-PAO" in skus
    pao = next(d for d in demand if d["sku"] == "F4-PAO")
    assert Decimal(pao["units_sold_lookback"]) == Decimal("50.000")
    assert Decimal(pao["forecast_units"]) > 0

    sug = production_and_purchase_suggestions(tenant=tenant_a)
    assert any(p["sku"] == "F4-PAO" for p in sug["production"])
    # compra de farinha se sugestão de produção
    # (pode ou não faltar farinha — stock 500 é alto; production still suggested by min)


@pytest.mark.django_db
def test_customer_scores_and_pricing(tenant_a, catalog):
    scores = customer_intelligence(tenant=tenant_a)
    assert len(scores) >= 1
    row = next(s for s in scores if s["customer_id"] == str(catalog["customer"].id))
    assert row["order_count"] == 5
    assert row["churn_risk_score"] >= 50
    assert row["clv_cents"] >= row["clv_historical_cents"]
    assert 0 <= row["repurchase_propensity_score"] <= 100

    pricing = dynamic_pricing_suggestions(tenant=tenant_a)
    # com pouco estoque de pão e demanda, pode sugerir uplift
    bread_price = next((p for p in pricing if p["sku"] == "F4-PAO"), None)
    assert bread_price is not None
    assert bread_price["price_cents"] == 1000


@pytest.mark.django_db
def test_intelligence_api(api_client, auth_header, tenant_a, catalog):
    full = api_client.get("/api/v1/food/intelligence", **auth_header)
    assert full.status_code == 200, full.content
    assert "demand_forecast" in full.data
    assert "summary" in full.data
    assert full.data["summary"]["customers_scored"] >= 1

    demand = api_client.get(
        "/api/v1/food/intelligence?section=demand", **auth_header
    )
    assert demand.status_code == 200
    assert "demand_forecast" in demand.data

    customers = api_client.get(
        "/api/v1/food/intelligence?section=customers", **auth_header
    )
    assert customers.status_code == 200
    assert len(customers.data["customer_intelligence"]) >= 1

    report = intelligence_report(tenant=tenant_a)
    assert report["summary"]["skus_with_demand"] >= 1
