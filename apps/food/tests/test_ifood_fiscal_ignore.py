"""Testes B7 — ignore fiscal iFood (HP-06)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.exceptions import FoodInvalidOrderError, FoodOrderNotFoundError
from apps.food.fiscal.emit import emit_food_order_nfce, emit_food_orders_batch
from apps.food.fiscal.ignore import ignore_food_order_fiscal
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
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
def mapped_order(tenant_a, nfce_settings, provider_sp):
    nfe = create_product(
        tenant=tenant_a,
        code="IGN-01",
        description="Item",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="IGN-SKU",
        name="Item ignore",
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
        external_order_id="IGN-ORDER",
        customer_name="Cliente",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


@pytest.mark.django_db
def test_hp_06_ignore_with_reason(mapped_order, tenant_a):
    order = ignore_food_order_fiscal(
        tenant=tenant_a,
        order_id=mapped_order.id,
        reason="Emitido manualmente no PDV",
        actor="test",
    )
    assert order.fiscal_status == FoodOrder.FiscalStatus.IGNORED
    assert order.fiscal_ignored_reason == "Emitido manualmente no PDV"
    assert order.fiscal_ignored_at is not None
    warnings = assess_food_order_fiscal_readiness(order)
    assert any(w["code"] == "ignored" for w in warnings)


@pytest.mark.django_db
def test_ignore_requires_reason(tenant_a, mapped_order):
    with pytest.raises(FoodInvalidOrderError, match="Motivo"):
        ignore_food_order_fiscal(
            tenant=tenant_a, order_id=mapped_order.id, reason="  "
        )


@pytest.mark.django_db
def test_ignore_not_found(tenant_a):
    with pytest.raises(FoodOrderNotFoundError):
        ignore_food_order_fiscal(
            tenant=tenant_a,
            order_id="00000000-0000-0000-0000-000000000099",
            reason="x",
        )


@pytest.mark.django_db
def test_ignore_rejects_authorized(tenant_a, mapped_order, nfce_settings, provider_sp):
    emit_food_orders_batch(
        tenant=tenant_a, order_ids=[mapped_order.id], actor="test"
    )
    mapped_order.refresh_from_db()
    assert mapped_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    with pytest.raises(FoodInvalidOrderError, match="autorizada"):
        ignore_food_order_fiscal(
            tenant=tenant_a,
            order_id=mapped_order.id,
            reason="tarde demais",
        )


@pytest.mark.django_db
def test_reemit_after_ignore_clears_and_authorizes(
    tenant_a, mapped_order, nfce_settings, provider_sp
):
    ignore_food_order_fiscal(
        tenant=tenant_a,
        order_id=mapped_order.id,
        reason="Teste reemit",
    )
    mapped_order.refresh_from_db()
    assert mapped_order.fiscal_status == FoodOrder.FiscalStatus.IGNORED

    result = emit_food_order_nfce(
        tenant=tenant_a, order_id=mapped_order.id, actor="test"
    )
    assert result["status"] == "authorized"

    mapped_order.refresh_from_db()
    assert mapped_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert mapped_order.fiscal_ignored_reason == ""
    assert mapped_order.fiscal_ignored_at is None
    assert mapped_order.fiscal_emit_attempt >= 1


@pytest.mark.django_db
def test_api_ignore_and_list(
    api_client, auth_header, tenant_a, mapped_order
):
    resp = api_client.post(
        f"/api/v1/food/ifood/fiscal/{mapped_order.id}/ignore/",
        {"reason": "API ignore test"},
        format="json",
        **auth_header,
    )
    assert resp.status_code == 200, resp.content
    assert resp.data["fiscal_status"] == FoodOrder.FiscalStatus.IGNORED
    assert resp.data["fiscal_ignored_reason"] == "API ignore test"

    listing = api_client.get(
        "/api/v1/food/ifood/fiscal/?ignored_only=1",
        **auth_header,
    )
    assert listing.status_code == 200
    assert any(r["id"] == str(mapped_order.id) for r in listing.data["results"])


@pytest.mark.django_db
def test_api_ignore_missing_reason(api_client, auth_header, mapped_order):
    resp = api_client.post(
        f"/api/v1/food/ifood/fiscal/{mapped_order.id}/ignore/",
        {},
        format="json",
        **auth_header,
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_api_reemit_ignored_via_batch(
    api_client, auth_header, tenant_a, mapped_order, nfce_settings, provider_sp
):
    api_client.post(
        f"/api/v1/food/ifood/fiscal/{mapped_order.id}/ignore/",
        {"reason": "depois emite"},
        format="json",
        **auth_header,
    )
    emit = api_client.post(
        "/api/v1/food/ifood/emit-batch/",
        {"order_ids": [str(mapped_order.id)], "async": False},
        format="json",
        **auth_header,
    )
    assert emit.status_code == 200
    assert emit.data["authorized"] == 1
    mapped_order.refresh_from_db()
    assert mapped_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED


@pytest.mark.django_db
def test_ignore_rejects_processing(tenant_a, mapped_order):
    mapped_order.fiscal_status = FoodOrder.FiscalStatus.PROCESSING
    mapped_order.save(update_fields=["fiscal_status"])
    with pytest.raises(FoodInvalidOrderError, match="andamento"):
        ignore_food_order_fiscal(
            tenant=tenant_a,
            order_id=mapped_order.id,
            reason="não pode",
        )


@pytest.mark.django_db
def test_ignore_rejects_non_ifood_channel(tenant_a, mapped_order):
    mapped_order.channel = FoodOrder.Channel.WHATSAPP
    mapped_order.save(update_fields=["channel"])
    with pytest.raises(FoodInvalidOrderError, match="iFood"):
        ignore_food_order_fiscal(
            tenant=tenant_a,
            order_id=mapped_order.id,
            reason="canal errado",
        )
