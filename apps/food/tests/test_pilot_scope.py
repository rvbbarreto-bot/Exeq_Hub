"""Escopo piloto Food — Hub e Admin."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.food.hub_forms import parse_order_lines
from apps.food.models import FoodCustomer, FoodOrder, FoodProduct
from apps.food.pilot_scope import (
    PILOT_ADMIN_MODELS,
    PILOT_HUB_SECTIONS,
    admin_model_in_pilot,
    hub_section_in_pilot,
)
from apps.food.services import create_food_customer, create_food_product
from django.http import QueryDict


@pytest.fixture
def hub_food_pilot(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="food-pilot-qa",
        legal_name="Food Pilot QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="food.pilot@exeq.local", password="Secret123!", name="Food Pilot"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    create_food_customer(
        tenant=tenant,
        name="Cliente Piloto",
        phone_e164="+5511999990001",
        document="52998224725",
    )
    create_food_product(
        tenant=tenant,
        sku="PILOT-01",
        name="Item piloto",
        price_cents=500,
        cost_cents=200,
        unit="un",
        initial_stock="100",
    )
    return {"tenant": tenant, "user": user}


def _login(client, ctx):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


def test_pilot_scope_constants():
    assert "orders" in PILOT_HUB_SECTIONS
    assert "products" in PILOT_HUB_SECTIONS
    assert "customers" in PILOT_HUB_SECTIONS
    assert "production" in PILOT_HUB_SECTIONS
    assert "purchases" not in PILOT_HUB_SECTIONS
    assert hub_section_in_pilot("orders")
    assert not hub_section_in_pilot("marketplace")
    assert admin_model_in_pilot("FoodProduct")
    assert not admin_model_in_pilot("FoodCampaign")
    assert "FoodPayment" in PILOT_ADMIN_MODELS


def test_parse_order_lines_multi():
    post = QueryDict(mutable=True)
    post.setlist("line_product_id", ["a", "b"])
    post.setlist("line_quantity", ["2", "1.5"])
    lines = parse_order_lines(post)
    assert len(lines) == 2
    assert lines[0]["product_id"] == "a"
    assert str(lines[1]["quantity"]) == "1.5"


def test_parse_order_lines_legacy_single():
    post = QueryDict("product_id=x&quantity=3")
    lines = parse_order_lines(post)
    assert len(lines) == 1
    assert lines[0]["product_id"] == "x"


@pytest.mark.django_db
def test_hub_subnav_hides_out_of_pilot_sections(client, hub_food_pilot):
    _login(client, hub_food_pilot)
    r = client.get(reverse("hub-v4-food-orders"))
    assert r.status_code == 200
    body = r.content.decode()
    assert "Produtos" in body
    assert "Clientes" in body
    assert "Compras" not in body
    assert "Inteligência" not in body
    assert "btn--future" not in body


@pytest.mark.django_db
def test_hub_out_of_pilot_returns_404_page(client, hub_food_pilot):
    _login(client, hub_food_pilot)
    for url_name in (
        "hub-v4-food-purchases",
        "hub-v4-food-intelligence",
        "hub-v4-food-retention",
        "hub-v4-food-marketplace",
    ):
        r = client.get(reverse(url_name))
        assert r.status_code == 404
        assert "Fora do piloto" in r.content.decode()


@pytest.mark.django_db
def test_hub_pilot_sections_accessible(client, hub_food_pilot):
    _login(client, hub_food_pilot)
    for url_name in (
        "hub-v4-food-orders",
        "hub-v4-food-products",
        "hub-v4-food-customers",
        "hub-v4-food-production",
    ):
        assert client.get(reverse(url_name)).status_code == 200


@pytest.mark.django_db
def test_admin_food_index_hides_out_of_pilot_models(client, hub_food_pilot):
    user = hub_food_pilot["user"]
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(user)
    r = client.get(reverse("admin:app_list", args=["food"]))
    assert r.status_code == 200
    body = r.content.decode()
    assert "Campanha" not in body
    assert "Produto" in body or "Produtos Food" in body


@pytest.mark.django_db
def test_admin_out_of_pilot_model_blocked(client, hub_food_pilot):
    user = hub_food_pilot["user"]
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(user)
    r = client.get(reverse("admin:food_foodcampaign_changelist"))
    assert r.status_code == 302
    assert reverse("admin:app_list", args=["food"]) in r["Location"]


@pytest.mark.django_db
def test_hub_multi_item_order_create(client, hub_food_pilot):
    tenant = hub_food_pilot["tenant"]
    customer = FoodCustomer.objects.get(tenant=tenant)
    product_a = FoodProduct.objects.get(tenant=tenant, sku="PILOT-01")
    product_b = create_food_product(
        tenant=tenant,
        sku="PILOT-02",
        name="Baguete",
        price_cents=200,
        cost_cents=80,
        unit="un",
        initial_stock="50",
    )
    _login(client, hub_food_pilot)
    r = client.post(
        reverse("hub-v4-food-order-new"),
        {
            "customer_id": str(customer.id),
            "channel": FoodOrder.Channel.COUNTER,
            "line_product_id": [str(product_a.id), str(product_b.id)],
            "line_quantity": ["2", "1"],
            "idempotency_key": "hub-multi-1",
            "await_pix": "0",
        },
    )
    assert r.status_code == 302
    order = FoodOrder.objects.get(tenant=tenant, idempotency_key="hub-multi-1")
    assert order.lines.count() == 2
