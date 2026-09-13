"""EPIC-4 — Hub UI pagamento Food."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.food.models import FoodOrder
from apps.food.payments.router import PROVIDER_MERCADOPAGO
from apps.food.payments.services import create_payment_intent_for_order
from apps.food.services import create_food_customer, create_food_product, create_order


@pytest.fixture
def hub_payment_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="food-pay-ui",
        legal_name="Food Pay UI",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="pay.ui@exeq.local", password="Secret123!", name="Pay UI"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    return {"tenant": tenant, "user": user}


def _login(client, ctx):
    client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_order_detail_shows_mp_pix(client, hub_payment_ctx, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    tenant = hub_payment_ctx["tenant"]
    tenant.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant.save(update_fields=["settings"])

    customer = create_food_customer(
        tenant=tenant,
        name="UI Cliente",
        document="52998224725",
        email="ui@example.com",
    )
    product = create_food_product(
        tenant=tenant,
        sku="UI-01",
        name="Item UI",
        price_cents=5000,
        initial_stock=Decimal("3"),
    )
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="hub-ui-mp-1",
        await_pix=True,
    )
    create_payment_intent_for_order(tenant=tenant, order_id=order.id, method="pix")

    _login(client, hub_payment_ctx)
    response = client.get(reverse("hub-v4-food-order-detail", args=[order.id]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Mercado Pago" in body
    assert "000201" in body
    assert "Copiar Pix" in body
    assert "Gerar pagamento Pix" not in body


@pytest.mark.django_db
def test_hub_mp_email_warning(client, hub_payment_ctx, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    tenant = hub_payment_ctx["tenant"]
    tenant.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant.save(update_fields=["settings"])

    customer = create_food_customer(
        tenant=tenant,
        name="Sem Email UI",
        document="52998224725",
        email="",
    )
    product = create_food_product(
        tenant=tenant,
        sku="UI-02",
        name="Item UI 2",
        price_cents=5000,
    )
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="hub-ui-no-email",
        await_pix=True,
    )

    _login(client, hub_payment_ctx)
    response = client.get(reverse("hub-v4-food-order-detail", args=[order.id]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "exige e-mail" in body.lower() or "e-mail do cliente" in body.lower()
    assert "Gerar pagamento Pix" not in body


@pytest.mark.django_db
def test_hub_inter_generate_pix_button(client, hub_payment_ctx, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    tenant = hub_payment_ctx["tenant"]
    customer = create_food_customer(
        tenant=tenant,
        name="Inter UI",
        document="52998224725",
    )
    product = create_food_product(
        tenant=tenant,
        sku="UI-INT",
        name="Item Inter",
        price_cents=5000,
    )
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="hub-ui-inter",
        await_pix=True,
    )

    _login(client, hub_payment_ctx)
    response = client.get(reverse("hub-v4-food-order-detail", args=[order.id]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Inter (BolePix)" in body
    assert "Gerar pagamento Pix" in body


@pytest.mark.django_db
def test_hub_mp_card_form_stub(client, hub_payment_ctx, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    tenant = hub_payment_ctx["tenant"]
    tenant.settings = {"food_payment_provider": PROVIDER_MERCADOPAGO}
    tenant.save(update_fields=["settings"])

    customer = create_food_customer(
        tenant=tenant,
        name="Card UI",
        document="52998224725",
        email="card-ui@example.com",
    )
    product = create_food_product(
        tenant=tenant,
        sku="UI-CARD",
        name="Item Card",
        price_cents=5000,
        initial_stock=3,
    )
    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="hub-ui-card",
        await_pix=True,
    )

    _login(client, hub_payment_ctx)
    detail = client.get(reverse("hub-v4-food-order-detail", args=[order.id]))
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "Pagar com cartão" in body

    pay = client.post(
        reverse("hub-v4-food-order-detail", args=[order.id]),
        {
            "action": "card",
            "card_token": "stub_card_token",
            "payment_method_id": "visa",
            "installments": "1",
        },
    )
    assert pay.status_code == 302
    order.refresh_from_db()
    assert order.payment_status == FoodOrder.PaymentStatus.PAID
