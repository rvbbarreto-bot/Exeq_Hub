"""Food V1.1 — cupom rastreado + régua de retenção."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification
from apps.food.models import (
    FoodCouponRedemption,
    FoodOrder,
    FoodRetentionDispatch,
    FoodRetentionEnrollment,
)
from apps.food.retention import (
    create_coupon,
    create_retention_rule,
    food_dashboard_metrics,
    process_retention_tick,
)
from apps.food.services import create_food_customer, create_food_product, create_order


@pytest.fixture
def food_customer(tenant_a):
    c = create_food_customer(
        tenant=tenant_a,
        name="Inativo",
        phone_e164="+5511977776666",
        document="52998224725",
    )
    # Simula inatividade: última compra há 40 dias
    FoodCustomer = c.__class__
    FoodCustomer.objects.filter(pk=c.pk).update(
        last_order_at=timezone.now() - timedelta(days=40),
        created_at=timezone.now() - timedelta(days=90),
    )
    c.refresh_from_db()
    return c


@pytest.fixture
def product(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="RET-01",
        name="Item retenção",
        price_cents=10000,
        initial_stock=Decimal("100"),
    )


@pytest.mark.django_db
def test_coupon_tracks_campaign_to_sale(tenant_a, food_customer, product):
    from apps.food.retention import create_campaign

    camp = create_campaign(tenant=tenant_a, name="Volta", code="volta")
    coupon = create_coupon(
        tenant=tenant_a,
        code="VOLTA10",
        discount_type="percent",
        percent_bps=1000,
        campaign=camp,
    )
    order = create_order(
        tenant=tenant_a,
        customer_id=food_customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="coupon-order-1",
        coupon_code="volta10",
        await_pix=False,
    )
    assert order.discount_cents == 1000
    assert order.total_cents == 9000
    assert order.coupon_id == coupon.id
    redemption = FoodCouponRedemption.objects.get(order=order)
    assert redemption.campaign_id == camp.id
    assert redemption.discount_cents == 1000
    coupon.refresh_from_db()
    assert coupon.redemption_count == 1


@pytest.mark.django_db
def test_retention_rule_enroll_fire_and_reset_on_purchase(
    tenant_a, food_customer, product, settings
):
    settings.EVOLUTION_HTTP_MODE = "stub"
    settings.CHANNEL_AI_MODE = "stub"
    coupon = create_coupon(
        tenant=tenant_a,
        code="BACK5",
        discount_type="fixed_cents",
        amount_cents=500,
    )
    rule = create_retention_rule(
        tenant=tenant_a,
        name="Inativos 30d",
        kind="inactivity",
        inactivity_days=30,
        steps=[
            {
                "sequence": 1,
                "delay_days": 0,
                "message_template": "Oi {name}, use {coupon_code}",
                "coupon_id": coupon.id,
            },
            {
                "sequence": 2,
                "delay_days": 7,
                "message_template": "Ainda pensamos em você, {name}",
            },
        ],
    )
    # enroll + fire first step immediately
    result = process_retention_tick(tenant=tenant_a)
    assert result["enrolled"] == 1
    assert result["fired"] == 1
    enrollment = FoodRetentionEnrollment.objects.get(rule=rule, customer=food_customer)
    assert enrollment.status == FoodRetentionEnrollment.Status.ACTIVE
    assert enrollment.next_sequence == 2
    dispatch = FoodRetentionDispatch.objects.get(enrollment=enrollment, step__sequence=1)
    assert dispatch.status == FoodRetentionDispatch.Status.SENT
    assert "Inativo" in dispatch.message_body
    assert "BACK5" in dispatch.message_body
    assert ChannelNotification.objects.filter(tenant=tenant_a).exists()

    # idempotência: re-tick não reenvia step 1
    process_retention_tick(tenant=tenant_a)
    assert FoodRetentionDispatch.objects.filter(enrollment=enrollment).count() == 1

    # compra no meio da régua → stop
    create_order(
        tenant=tenant_a,
        customer_id=food_customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="buy-mid-rule",
        await_pix=False,
    )
    enrollment.refresh_from_db()
    assert enrollment.status == FoodRetentionEnrollment.Status.STOPPED
    assert enrollment.stop_reason == "purchase"


@pytest.mark.django_db
def test_dashboard_metrics(tenant_a, food_customer, product):
    create_order(
        tenant=tenant_a,
        customer_id=food_customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="dash-1",
        await_pix=False,
    )
    metrics = food_dashboard_metrics(tenant=tenant_a)
    assert metrics["orders_paid"] == 1
    assert metrics["revenue_cents"] == 10000
    assert metrics["customers_active"] >= 1


@pytest.mark.django_db
def test_api_coupon_rule_dashboard_tick(
    api_client, auth_header, tenant_a, food_customer, product, settings
):
    settings.EVOLUTION_HTTP_MODE = "stub"
    coupon = api_client.post(
        "/api/v1/food/coupons/",
        {
            "code": "API10",
            "discount_type": "percent",
            "percent_bps": 1000,
        },
        format="json",
        **auth_header,
    )
    assert coupon.status_code == 201, coupon.content
    rule = api_client.post(
        "/api/v1/food/retention-rules/",
        {
            "name": "API Rule",
            "kind": "inactivity",
            "inactivity_days": 30,
            "steps": [
                {
                    "sequence": 1,
                    "delay_days": 0,
                    "message_template": "Volta {name}",
                }
            ],
        },
        format="json",
        **auth_header,
    )
    assert rule.status_code == 201, rule.content
    tick = api_client.post(
        "/api/v1/food/retention-rules/tick/",
        {},
        format="json",
        **auth_header,
    )
    assert tick.status_code == 200, tick.content
    assert tick.data["enrolled"] >= 1
    dash = api_client.get("/api/v1/food/dashboard", **auth_header)
    assert dash.status_code == 200
    assert "revenue_cents" in dash.data
