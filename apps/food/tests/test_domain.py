from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.food.exceptions import (
    FoodInsufficientStockError,
    FoodInvalidOrderError,
    FoodProductNotFoundError,
)
from apps.food.models import FoodOrder, FoodStockBalance
from apps.food.services import (
    apply_stock_movement,
    create_food_customer,
    create_food_product,
    create_order,
    mark_order_paid_by_pix,
)


@pytest.fixture
def customer(tenant_a):
    return create_food_customer(
        tenant=tenant_a,
        name="Maria Padaria",
        phone_e164="+5511999990001",
    )


@pytest.fixture
def product(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="PAO-FRA",
        name="Pão francês kg",
        price_cents=1200,
        cost_cents=400,
        category="padaria",
        unit="kg",
        initial_stock=Decimal("10"),
        min_quantity=Decimal("2"),
    )


@pytest.mark.django_db
def test_create_customer_and_product(customer, product, tenant_a):
    assert customer.phone_e164.startswith("+55")
    balance = FoodStockBalance.objects.get(product=product)
    assert balance.quantity == Decimal("10")
    assert str(product).startswith("PAO-FRA")


@pytest.mark.django_db
def test_product_sku_unique_per_tenant(tenant_a, product):
    with pytest.raises(IntegrityError):
        create_food_product(
            tenant=tenant_a,
            sku="PAO-FRA",
            name="Duplicado",
            price_cents=100,
        )


@pytest.mark.django_db
def test_create_order_whatsapp_idempotent(tenant_a, customer, product):
    kwargs = dict(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1.5"}],
        idempotency_key="wa-msg-001",
        await_pix=True,
    )
    o1 = create_order(**kwargs)
    o2 = create_order(**kwargs)
    assert o1.id == o2.id
    assert o1.status == FoodOrder.Status.PENDING_PAYMENT
    assert o1.payment_status == FoodOrder.PaymentStatus.AWAITING_PIX
    assert o1.total_cents == 1800  # 12.00 * 1.5
    assert o1.lines.count() == 1
    line = o1.lines.get()
    assert line.sku == "PAO-FRA"
    assert line.quantity == Decimal("1.5")


@pytest.mark.django_db
def test_create_order_counter_paid_deducts_stock(tenant_a, customer, product):
    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "2"}],
        idempotency_key="counter-001",
        await_pix=False,
    )
    assert order.payment_status == FoodOrder.PaymentStatus.PAID
    assert order.status == FoodOrder.Status.CONFIRMED
    product.stock_balance.refresh_from_db()
    assert product.stock_balance.quantity == Decimal("8")
    customer.refresh_from_db()
    assert customer.order_count == 1
    assert customer.total_spent_cents == 2400
    assert customer.avg_ticket_cents == 2400


@pytest.mark.django_db
def test_mark_order_paid_by_pix_deducts_once(tenant_a, customer, product):
    order = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="pix-001",
        await_pix=True,
    )
    paid = mark_order_paid_by_pix(
        tenant=tenant_a, order_id=order.id, pix_txid="TXID-XYZ"
    )
    again = mark_order_paid_by_pix(
        tenant=tenant_a, order_id=order.id, pix_txid="TXID-XYZ"
    )
    assert paid.id == again.id
    assert paid.payment_status == FoodOrder.PaymentStatus.PAID
    assert paid.pix_txid == "TXID-XYZ"
    product.stock_balance.refresh_from_db()
    assert product.stock_balance.quantity == Decimal("9")
    customer.refresh_from_db()
    assert customer.order_count == 1


@pytest.mark.django_db
def test_insufficient_stock(tenant_a, customer, product):
    with pytest.raises(FoodInsufficientStockError):
        create_order(
            tenant=tenant_a,
            customer_id=customer.id,
            channel=FoodOrder.Channel.COUNTER,
            lines=[{"product_id": product.id, "quantity": "50"}],
            idempotency_key="big-001",
            await_pix=False,
        )


@pytest.mark.django_db
def test_invalid_channel_and_empty_lines(tenant_a, customer, product):
    with pytest.raises(FoodInvalidOrderError):
        create_order(
            tenant=tenant_a,
            customer_id=customer.id,
            channel="not_a_channel",
            lines=[{"product_id": product.id, "quantity": "1"}],
            idempotency_key="x1",
        )
    with pytest.raises(FoodInvalidOrderError):
        create_order(
            tenant=tenant_a,
            customer_id=customer.id,
            channel=FoodOrder.Channel.COUNTER,
            lines=[],
            idempotency_key="x2",
        )


@pytest.mark.django_db
def test_inactive_product_rejected(tenant_a, customer, product):
    product.is_active = False
    product.save(update_fields=["is_active"])
    with pytest.raises(FoodProductNotFoundError):
        create_order(
            tenant=tenant_a,
            customer_id=customer.id,
            channel=FoodOrder.Channel.COUNTER,
            lines=[{"product_id": product.id, "quantity": "1"}],
            idempotency_key="inactive-1",
            await_pix=False,
        )


@pytest.mark.django_db
def test_stock_in_movement(tenant_a, product):
    bal = apply_stock_movement(
        tenant=tenant_a,
        product=product,
        movement_type="in",
        quantity=Decimal("3"),
        reason="compra",
    )
    assert bal.quantity == Decimal("13")


@pytest.mark.django_db
def test_order_channel_is_attribute_not_separate_entity(tenant_a, customer, product):
    wa = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.WHATSAPP,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="ch-wa",
        await_pix=True,
    )
    counter = create_order(
        tenant=tenant_a,
        customer_id=customer.id,
        channel=FoodOrder.Channel.COUNTER,
        lines=[{"product_id": product.id, "quantity": "1"}],
        idempotency_key="ch-counter",
        await_pix=True,
    )
    assert type(wa) is type(counter) is FoodOrder
    assert set(FoodOrder.objects.filter(tenant=tenant_a).values_list("channel", flat=True)) == {
        "whatsapp",
        "counter",
    }
