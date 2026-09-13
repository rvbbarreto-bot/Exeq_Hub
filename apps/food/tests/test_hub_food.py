"""Hub V4 — Food: pedidos, compras, produção e inteligência."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.food.models import FoodOrder, FoodPurchase
from apps.food.services import create_food_customer, create_food_product, create_order


@pytest.fixture
def hub_food(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="food-hub-qa",
        legal_name="Food Hub QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="food.hub@exeq.local", password="Secret123!", name="Food Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    customer = create_food_customer(
        tenant=tenant,
        name="Cliente Hub Food",
        phone_e164="+5511999990000",
        document="52998224725",
    )
    product = create_food_product(
        tenant=tenant,
        sku="PATE-01",
        name="Pão francês",
        price_cents=100,
        cost_cents=40,
        unit="un",
        initial_stock=Decimal("100"),
    )
    return {
        "tenant": tenant,
        "user": user,
        "customer": customer,
        "product": product,
    }


def _login(client, ctx):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_food_orders_list_and_detail(client, hub_food):
    _login(client, hub_food)
    order = create_order(
        tenant=hub_food["tenant"],
        customer_id=hub_food["customer"].id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": hub_food["product"].id, "quantity": "2"}],
        idempotency_key="hub-food-list-1",
        await_pix=False,
        deduct_stock=True,
    )
    r = client.get(reverse("hub-v4-food-orders"))
    assert r.status_code == 200
    body = r.content.decode()
    assert "Pedidos" in body
    assert "Produtos" in body
    assert "Compras" not in body
    assert hub_food["customer"].name in body

    detail = client.get(reverse("hub-v4-food-order-detail", args=[order.id]))
    assert detail.status_code == 200
    assert "Pão francês" in detail.content.decode() or "PATE-01" in detail.content.decode()


@pytest.mark.django_db
def test_hub_food_purchase_create_and_receive(client, hub_food):
    _login(client, hub_food)
    r = client.post(
        reverse("hub-v4-food-purchase-new"),
        {
            "action": "create",
            "supplier_id": "__new__",
            "supplier_name": "Atacado Hub",
            "supplier_document": "11222333000181",
            "product_id": str(hub_food["product"].id),
            "quantity": "10",
            "unit_cost": "80",
            "idempotency_key": "hub-purch-test-1",
        },
    )
    assert r.status_code == 404
    assert not FoodPurchase.objects.filter(
        tenant=hub_food["tenant"], idempotency_key="hub-purch-test-1"
    ).exists()


@pytest.mark.django_db
def test_hub_food_intelligence_and_production_pages(client, hub_food):
    _login(client, hub_food)
    intel = client.get(reverse("hub-v4-food-intelligence"))
    assert intel.status_code == 404

    prod = client.get(reverse("hub-v4-food-production"))
    assert prod.status_code == 200
    assert "Produção" in prod.content.decode() or "ordem" in prod.content.decode().lower()


@pytest.mark.django_db
def test_hub_food_order_transition(client, hub_food):
    _login(client, hub_food)
    order = create_order(
        tenant=hub_food["tenant"],
        customer_id=hub_food["customer"].id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": hub_food["product"].id, "quantity": "1"}],
        idempotency_key="hub-food-trans-1",
        await_pix=False,
        deduct_stock=True,
    )
    assert order.status == FoodOrder.Status.CONFIRMED
    r = client.post(
        reverse("hub-v4-food-order-detail", args=[order.id]),
        {"action": "transition", "status": FoodOrder.Status.PREPARING},
    )
    assert r.status_code == 302
    order.refresh_from_db()
    assert order.status == FoodOrder.Status.PREPARING


@pytest.mark.django_db
def test_hub_food_retention_create_and_tick(client, hub_food):
    from apps.food.models import FoodRetentionRule

    _login(client, hub_food)
    r = client.post(
        reverse("hub-v4-food-retention"),
        {
            "action": "create_rule",
            "name": "Inativos Hub",
            "kind": "inactivity",
            "inactivity_days": "1",
            "steps_text": "0|Oi {name} volte",
        },
    )
    assert r.status_code == 404
    assert not FoodRetentionRule.objects.filter(
        tenant=hub_food["tenant"], name="Inativos Hub"
    ).exists()


@pytest.mark.django_db
def test_hub_food_marketplace_upsert_and_sync(client, hub_food, settings):
    from apps.food.models import FoodMarketplaceConnection, FoodOrder

    settings.MARKETPLACE_HTTP_MODE = "stub"
    _login(client, hub_food)
    r = client.post(
        reverse("hub-v4-food-marketplace"),
        {
            "action": "upsert",
            "provider": "ifood",
            "merchant_ref": "hub-loja",
            "http_mode": "stub",
            "is_active": "1",
        },
    )
    assert r.status_code == 404
    assert not FoodMarketplaceConnection.objects.filter(
        tenant=hub_food["tenant"], merchant_ref="hub-loja"
    ).exists()
    assert not FoodOrder.objects.filter(
        tenant=hub_food["tenant"], channel_ref="HUB-MP-1"
    ).exists()
