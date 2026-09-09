"""Testes B3 — de-para FoodProduct → NfeProduct."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_orders_batch
from apps.food.fiscal.mapping import (
    is_food_order_fiscally_ready,
    set_food_product_nfe_mapping,
)
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfe.models import NfeProduct
from apps.nfe.services import create_product
from integrations.marketplace.normalize import normalize_marketplace_order


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
def food_product_unmapped(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="MAP-SKU",
        name="Item map",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("20"),
    )


@pytest.fixture
def nfe_product(tenant_a, nfce_settings):
    return create_product(
        tenant=tenant_a,
        code="FISCAL-MAP",
        description="Item fiscal",
        ncm="21069090",
        unit_price_cents=9999,
        csosn="102",
    )


@pytest.fixture
def ifood_order_unmapped(tenant_a, food_product_unmapped):
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="MAP-ORDER-1",
        customer_name="Cliente",
        customer_phone="+5511955554444",
        lines=[{"sku": food_product_unmapped.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


@pytest.mark.django_db
def test_ex_map_02_unmapped_warning(ifood_order_unmapped):
    warnings = assess_food_order_fiscal_readiness(ifood_order_unmapped)
    codes = {w["code"] for w in warnings}
    assert "nfe_product_unmapped" in codes
    assert not is_food_order_fiscally_ready(ifood_order_unmapped)


@pytest.mark.django_db
def test_hp_02_map_clears_warning(
    nfce_settings, provider_sp, tenant_a, ifood_order_unmapped, nfe_product, food_product_unmapped
):
    set_food_product_nfe_mapping(
        tenant=tenant_a,
        product=food_product_unmapped,
        nfe_product_id=nfe_product.id,
    )
    ifood_order_unmapped.refresh_from_db()
    warnings = assess_food_order_fiscal_readiness(ifood_order_unmapped)
    codes = {w["code"] for w in warnings}
    assert "nfe_product_unmapped" not in codes
    assert is_food_order_fiscally_ready(ifood_order_unmapped)


@pytest.mark.django_db
def test_ex_map_08_recalc_on_map_change(tenant_a, ifood_order_unmapped, nfe_product, food_product_unmapped):
    assert "nfe_product_unmapped" in {
        w["code"] for w in (ifood_order_unmapped.fiscal_warnings or [])
    }
    set_food_product_nfe_mapping(
        tenant=tenant_a,
        product=food_product_unmapped,
        nfe_product_id=nfe_product.id,
    )
    ifood_order_unmapped.refresh_from_db()
    codes = {w["code"] for w in (ifood_order_unmapped.fiscal_warnings or [])}
    assert "nfe_product_unmapped" not in codes


@pytest.mark.django_db
def test_ex_map_01_mapped_emit(
    nfce_settings, tenant_a, provider_sp, ifood_order_unmapped, nfe_product, food_product_unmapped
):
    set_food_product_nfe_mapping(
        tenant=tenant_a,
        product=food_product_unmapped,
        nfe_product_id=nfe_product.id,
    )
    result = emit_food_orders_batch(
        tenant=tenant_a, order_ids=[ifood_order_unmapped.id], actor="test"
    )
    assert result["authorized"] == 1
    ifood_order_unmapped.refresh_from_db()
    assert ifood_order_unmapped.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED


@pytest.mark.django_db
def test_ex_map_06_order_price_prevails_over_nfe_catalog(
    ifood_order_unmapped, nfe_product, food_product_unmapped, tenant_a
):
    """Preço da linha do pedido (1500) prevalece sobre NfeProduct (9999)."""
    from apps.food.fiscal.adapter import build_nfce_items_from_food_order

    set_food_product_nfe_mapping(
        tenant=tenant_a,
        product=food_product_unmapped,
        nfe_product_id=nfe_product.id,
    )
    items = build_nfce_items_from_food_order(ifood_order_unmapped)
    assert items[0]["unit_price_cents"] == 1500
    assert items[0]["product_id"] == str(nfe_product.id)


@pytest.mark.django_db
def test_normalize_external_code_via_sku_map():
    raw = {
        "external_order_id": "EXT-1",
        "lines": [{"external_code": "IFOOD-CODE", "quantity": 1, "unit_price_cents": 1500}],
    }
    out = normalize_marketplace_order(
        provider="ifood",
        raw=raw,
        sku_map={"IFOOD-CODE": "MAP-SKU"},
    )
    assert out["lines"][0]["sku"] == "MAP-SKU"


@pytest.mark.django_db
def test_api_patch_nfe_product_mapping(
    api_client, auth_header, tenant_a, food_product_unmapped, nfe_product
):
    resp = api_client.patch(
        f"/api/v1/food/products/{food_product_unmapped.id}/",
        {"nfe_product_id": str(nfe_product.id)},
        format="json",
        **auth_header,
    )
    assert resp.status_code == 200, resp.content
    assert resp.data["nfe_product_id"] == str(nfe_product.id)
    assert resp.data["nfe_product_code"] == "FISCAL-MAP"
    food_product_unmapped.refresh_from_db()
    assert food_product_unmapped.nfe_product_id == nfe_product.id
