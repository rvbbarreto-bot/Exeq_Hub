"""Testes B8 — polish Hub fiscal iFood (filtros, sync cancel, painel)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import TenantMembership
from apps.accounts.services import ensure_system_roles
from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_order_nfce
from apps.food.fiscal.hub_context import food_order_fiscal_panel_context
from apps.food.fiscal.hub_filters import filter_ifood_fiscal_orders
from apps.food.fiscal.nfce_sync import (
    cancel_nfce_for_food_order,
    sync_food_orders_after_nfce_cancel,
)
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfce.services import cancel_nfce
from apps.nfe.services import create_product


@pytest.fixture
def nfce_settings(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings", "updated_at"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ FOOD LAB",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )


@pytest.fixture
def hub_user(tenant_a):
    from apps.accounts.models import User

    roles = {r.code: r for r in ensure_system_roles()}
    user = User.objects.create_user(
        email="b8.hub@exeq.local", password="Secret123!", name="B8 Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant_a, user=user, role=roles["tenant_admin"], is_active=True
    )
    return user


def _login(client, tenant_a, user):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant_a.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )


@pytest.fixture
def mapped_ifood_order(tenant_a, nfce_settings, provider_sp):
    nfe = create_product(
        tenant=tenant_a,
        code="B8-01",
        description="Item B8",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="B8-SKU",
        name="Prato B8",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("20"),
    )
    food.nfe_product = nfe
    food.save(update_fields=["nfe_product"])
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="B8-REF-001",
        customer_name="Cliente B8",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


@pytest.fixture
def unmapped_ifood_order(tenant_a, nfce_settings, provider_sp):
    create_food_product(
        tenant=tenant_a,
        sku="B8-UNMAP",
        name="Sem de-para",
        price_cents=1000,
        cost_cents=400,
        unit="un",
        initial_stock=Decimal("10"),
    )
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="B8-REF-UNMAP",
        customer_name="Cliente unmap",
        customer_phone="+5511955553333",
        lines=[{"sku": "B8-UNMAP", "quantity": "1", "unit_price_cents": 1000}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


@pytest.mark.django_db
def test_filter_ifood_fiscal_ready_and_unmapped(
    tenant_a, mapped_ifood_order, unmapped_ifood_order
):
    base = FoodOrder.objects.filter(tenant=tenant_a, channel=FoodOrder.Channel.IFOOD)
    ready = filter_ifood_fiscal_orders(base, fiscal_filter="ready")
    assert mapped_ifood_order.id in ready.values_list("id", flat=True)
    assert unmapped_ifood_order.id not in ready.values_list("id", flat=True)

    unmapped = filter_ifood_fiscal_orders(base, mapping_filter="unmapped")
    assert unmapped_ifood_order.id in unmapped.values_list("id", flat=True)
    assert mapped_ifood_order.id not in unmapped.values_list("id", flat=True)

    by_ref = filter_ifood_fiscal_orders(base, q="B8-REF-001")
    assert by_ref.count() == 1
    assert by_ref.first().id == mapped_ifood_order.id


@pytest.mark.django_db
def test_sync_food_order_after_nfce_cancel(tenant_a, mapped_ifood_order, provider_sp):
    emit_food_order_nfce(
        tenant=tenant_a,
        order_id=mapped_ifood_order.id,
        actor="test",
    )
    mapped_ifood_order.refresh_from_db()
    assert mapped_ifood_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    inv = mapped_ifood_order.nfce_invoice
    cancel_nfce(inv, justificativa="Cancelamento teste B8 sync", actor="test")
    inv.refresh_from_db()
    assert sync_food_orders_after_nfce_cancel(inv) == 1
    mapped_ifood_order.refresh_from_db()
    assert mapped_ifood_order.fiscal_status == FoodOrder.FiscalStatus.CANCELLED


@pytest.mark.django_db
def test_cancel_nfce_for_food_order(tenant_a, mapped_ifood_order, provider_sp):
    emit_food_order_nfce(
        tenant=tenant_a,
        order_id=mapped_ifood_order.id,
        actor="test",
    )
    mapped_ifood_order.refresh_from_db()
    cancel_nfce_for_food_order(
        tenant=tenant_a,
        order=mapped_ifood_order,
        justificativa="Cancelamento via helper B8",
        actor="test",
    )
    mapped_ifood_order.refresh_from_db()
    assert mapped_ifood_order.fiscal_status == FoodOrder.FiscalStatus.CANCELLED
    assert mapped_ifood_order.nfce_invoice.status == NfceInvoice.Status.CANCELLED


@pytest.mark.django_db
def test_fiscal_panel_context_flags(tenant_a, mapped_ifood_order, provider_sp):
    ctx = food_order_fiscal_panel_context(mapped_ifood_order)
    assert ctx["fiscal_is_ifood"] is True
    assert ctx["fiscal_can_emit"] is True
    assert ctx["fiscal_can_cancel_nfce"] is False

    emit_food_order_nfce(
        tenant=tenant_a,
        order_id=mapped_ifood_order.id,
        actor="test",
    )
    mapped_ifood_order.refresh_from_db()
    ctx2 = food_order_fiscal_panel_context(mapped_ifood_order)
    assert ctx2["fiscal_can_emit"] is False
    assert ctx2["fiscal_can_cancel_nfce"] is True


@pytest.mark.django_db
def test_hub_ifood_fiscal_page_and_cancel(
    client, tenant_a, hub_user, mapped_ifood_order, provider_sp
):
    _login(client, tenant_a, hub_user)
    emit_food_order_nfce(
        tenant=tenant_a,
        order_id=mapped_ifood_order.id,
        actor="test",
    )
    mapped_ifood_order.refresh_from_db()

    listing = client.get(reverse("hub-v4-food-ifood-fiscal"))
    assert listing.status_code == 200
    body = listing.content.decode()
    assert "B8-REF-001" in body
    assert "Cancelar NFC-e" in body

    ready = client.get(reverse("hub-v4-food-ifood-fiscal") + "?fiscal=authorized")
    assert "B8-REF-001" in ready.content.decode()

    cancel = client.post(
        reverse("hub-v4-food-ifood-fiscal"),
        {
            "action": "cancel_nfce",
            "cancel_order_id": str(mapped_ifood_order.id),
            "justificativa": "Cancelamento hub B8 teste",
        },
    )
    assert cancel.status_code == 302
    mapped_ifood_order.refresh_from_db()
    assert mapped_ifood_order.fiscal_status == FoodOrder.FiscalStatus.CANCELLED


@pytest.mark.django_db
def test_hub_order_detail_fiscal_panel(
    client, tenant_a, hub_user, mapped_ifood_order
):
    _login(client, tenant_a, hub_user)
    detail = client.get(
        reverse("hub-v4-food-order-detail", args=[mapped_ifood_order.id])
    )
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "Fiscal iFood" in body
    assert "B8-REF-001" in body
    assert "Emitir NFC-e" in body
