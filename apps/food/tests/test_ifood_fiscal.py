"""Testes iFood fiscal → NFC-e (Opção B)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_orders_batch
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfe.models import NfeProduct
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
def mapped_food_product(tenant_a):
    nfe = NfeProduct.objects.create(
        tenant=tenant_a,
        code="IFOOD-01",
        description="Item iFood",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="IFOOD-SKU",
        name="Prato iFood",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("20"),
    )
    food.nfe_product = nfe
    food.save(update_fields=["nfe_product", "updated_at"])
    return food


@pytest.fixture
def mapped_food_product_emit(tenant_a, nfce_settings, provider_sp):
    return create_product(
        tenant=tenant_a,
        code="IFOOD-EMIT",
        description="Item iFood emit",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )


@pytest.fixture
def ifood_order_emit(tenant_a, mapped_food_product_emit):
    food = create_food_product(
        tenant=tenant_a,
        sku="IFOOD-EMIT-SKU",
        name="Prato emit",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("20"),
    )
    food.nfe_product = mapped_food_product_emit
    food.save(update_fields=["nfe_product", "updated_at"])
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="IFO-FISCAL-1",
        customer_name="Cliente iFood",
        customer_phone="+5511955554444",
        lines=[
            {
                "sku": food.sku,
                "quantity": "2",
                "unit_price_cents": 1500,
            }
        ],
        total_cents=3000,
        delivery_address="Rua A, 100",
        merchant_ref="loja-1",
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document", "updated_at"])
    return order


@pytest.fixture
def ifood_order(tenant_a, mapped_food_product):
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="IFO-FISCAL-1",
        customer_name="Cliente iFood",
        customer_phone="+5511955554444",
        lines=[
            {
                "sku": mapped_food_product.sku,
                "quantity": "2",
                "unit_price_cents": 1500,
            }
        ],
        total_cents=3000,
        delivery_address="Rua A, 100",
        merchant_ref="loja-1",
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document", "updated_at"])
    return order


@pytest.mark.django_db
def test_import_sets_fiscal_pending(ifood_order):
    """HP-01: ingestão define fiscal_status=PENDING."""
    assert ifood_order.channel == FoodOrder.Channel.IFOOD
    assert ifood_order.fiscal_status == FoodOrder.FiscalStatus.PENDING
    assert isinstance(ifood_order.fiscal_warnings, list)


@pytest.mark.django_db
def test_readiness_warns_unmapped_nfe_product(tenant_a, ifood_order):
    """EX-MAP: aviso quando produto fiscal não mapeado."""
    line = ifood_order.lines.select_related("product").first()
    product = line.product
    product.nfe_product = None
    product.save(update_fields=["nfe_product", "updated_at"])

    warnings = assess_food_order_fiscal_readiness(ifood_order)
    codes = {w["code"] for w in warnings}
    assert "nfe_product_unmapped" in codes


@pytest.mark.django_db
def test_emit_batch_authorizes(nfce_settings, tenant_a, provider_sp, ifood_order_emit):
    """HP-03 / EX-EMT: lote emite NFC-e stub e vincula pedido."""
    result = emit_food_orders_batch(
        tenant=tenant_a,
        order_ids=[ifood_order_emit.id],
        actor="test",
    )
    assert result["authorized"] == 1
    assert result["failed"] == 0

    ifood_order_emit.refresh_from_db()
    assert ifood_order_emit.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert ifood_order_emit.nfce_invoice_id is not None
    inv = ifood_order_emit.nfce_invoice
    assert inv.status == NfceInvoice.Status.AUTHORIZED


@pytest.mark.django_db
def test_emit_batch_partial_failure(nfce_settings, tenant_a, provider_sp):
    """EX-EMT-11 / PO-4: lote parcial — só falhos reprocessados."""
    nfe_ok = create_product(
        tenant=tenant_a,
        code="IFOOD-OK",
        description="Ok",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    nfe_bad = create_product(
        tenant=tenant_a,
        code="IFOOD-BAD",
        description="Bad",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food_ok = create_food_product(
        tenant=tenant_a,
        sku="SKU-OK",
        name="Ok",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("10"),
    )
    food_ok.nfe_product = nfe_ok
    food_ok.save(update_fields=["nfe_product"])
    food_bad = create_food_product(
        tenant=tenant_a,
        sku="SKU-BAD",
        name="Bad",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("10"),
    )
    food_bad.nfe_product = nfe_bad
    food_bad.save(update_fields=["nfe_product"])

    ok = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="IFO-OK",
        customer_name="Ok",
        customer_phone="+5511911111111",
        lines=[{"sku": food_ok.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    ok.customer.document = "39053344705"
    ok.customer.save(update_fields=["document"])
    bad = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="IFO-BAD",
        customer_name="Bad",
        customer_phone="+5511922222222",
        lines=[{"sku": food_bad.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    bad.customer.document = "39053344705"
    bad.customer.save(update_fields=["document"])
    food_bad.nfe_product = None
    food_bad.save(update_fields=["nfe_product"])

    result = emit_food_orders_batch(
        tenant=tenant_a,
        order_ids=[ok.id, bad.id],
        actor="test",
    )
    assert result["authorized"] == 1
    assert result["failed"] == 1

    ok.refresh_from_db()
    bad.refresh_from_db()
    assert ok.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert bad.fiscal_status == FoodOrder.FiscalStatus.FAILED


@pytest.mark.django_db
def test_emit_skips_already_authorized(nfce_settings, tenant_a, provider_sp, ifood_order_emit):
    emit_food_orders_batch(tenant=tenant_a, order_ids=[ifood_order_emit.id], actor="test")
    ifood_order_emit.refresh_from_db()
    first_inv = ifood_order_emit.nfce_invoice_id

    again = emit_food_orders_batch(
        tenant=tenant_a,
        order_ids=[ifood_order_emit.id],
        actor="test",
    )
    assert again["skipped"] == 1
    ifood_order_emit.refresh_from_db()
    assert ifood_order_emit.nfce_invoice_id == first_inv


@pytest.mark.django_db
def test_api_list_and_emit_batch(
    api_client, auth_header, nfce_settings, tenant_a, provider_sp, ifood_order_emit
):
    listing = api_client.get("/api/v1/food/ifood/fiscal/", **auth_header)
    assert listing.status_code == 200
    assert listing.data["count"] >= 1
    assert any(r["id"] == str(ifood_order_emit.id) for r in listing.data["results"])

    emit = api_client.post(
        "/api/v1/food/ifood/emit-batch/",
        {"order_ids": [str(ifood_order_emit.id)], "async": False},
        format="json",
        **auth_header,
    )
    assert emit.status_code == 200
    assert emit.data["authorized"] == 1

    detail = api_client.get(
        f"/api/v1/food/ifood/fiscal/{ifood_order_emit.id}/",
        **auth_header,
    )
    assert detail.status_code == 200
    assert detail.data["fiscal_status"] == FoodOrder.FiscalStatus.AUTHORIZED
    assert detail.data["nfce_invoice_id"]
