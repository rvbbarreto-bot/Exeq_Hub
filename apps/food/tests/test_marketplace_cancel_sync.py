"""B1 — sync cancelamento marketplace (EX-ING-07/08)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_orders_batch
from apps.food.fiscal.marketplace_sync import (
    apply_marketplace_logistic_sync,
    cancel_marketplace_order_logistic,
    find_marketplace_order,
)
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order, sync_marketplace_connection, upsert_marketplace_connection
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfe.models import NfeProduct
from apps.nfe.services import create_product
from integrations.marketplace.cancel import marketplace_payload_cancelled
from integrations.marketplace.normalize import normalize_marketplace_order


@pytest.fixture
def product(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="CAN-01",
        name="Item cancel",
        price_cents=1500,
        cost_cents=500,
        unit="un",
        initial_stock=Decimal("20"),
    )


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
        legal_name="LAB",
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
def ifood_order(tenant_a, product):
    food = product
    food.nfe_product = NfeProduct.objects.create(
        tenant=tenant_a,
        code="CAN-NFE",
        description="NFE",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food.save(update_fields=["nfe_product"])
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="CAN-100",
        customer_name="Cliente",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


def test_marketplace_payload_cancelled_detects_status():
    assert marketplace_payload_cancelled({"status": "CANCELLED"}) is True
    assert marketplace_payload_cancelled({"cancelled": True}) is True
    assert marketplace_payload_cancelled({"status": "PREPARING"}) is False


def test_normalize_cancel_only_payload():
    out = normalize_marketplace_order(
        provider="ifood",
        raw={"external_order_id": "CAN-ONLY", "cancelled": True},
        merchant_ref="loja",
    )
    assert out["cancelled"] is True
    assert out["lines"] == []
    assert out["external_order_id"] == "CAN-ONLY"


def test_normalize_ifood_like_cancelled_status():
    raw = {
        "id": "IFO-CAN",
        "status": "cancelled",
        "customer": {"name": "X"},
        "items": [{"sku": "CAN-01", "quantity": 1, "unitPrice": 10}],
    }
    out = normalize_marketplace_order(provider="ifood", raw=raw)
    assert out["cancelled"] is True


@pytest.mark.django_db
def test_ex_ing_07_cancel_pre_emission(tenant_a, ifood_order):
    """Cancel iFood pré-emissão: logístico cancelled, fiscal PENDING."""
    assert ifood_order.fiscal_status == FoodOrder.FiscalStatus.PENDING

    row = apply_marketplace_logistic_sync(
        tenant=tenant_a,
        provider="ifood",
        payload={
            "external_order_id": "CAN-100",
            "cancelled": True,
        },
    )
    assert row["action"] == "cancelled"

    ifood_order.refresh_from_db()
    assert ifood_order.status == FoodOrder.Status.CANCELLED
    assert ifood_order.fiscal_status == FoodOrder.FiscalStatus.PENDING
    codes = {w["code"] for w in assess_food_order_fiscal_readiness(ifood_order)}
    assert "order_logistic_cancelled" in codes
    assert "marketplace_cancelled_with_nfce" not in codes


@pytest.mark.django_db
def test_ex_ing_08_cancel_post_authorized_keeps_fiscal(
    tenant_a, ifood_order, nfce_settings, provider_sp
):
    """Cancel iFood pós-AUTHORIZED: aviso fiscal, NFC-e intacta (PO-3)."""
    emit_food_orders_batch(tenant=tenant_a, order_ids=[ifood_order.id], actor="test")
    ifood_order.refresh_from_db()
    assert ifood_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    nfce_id = ifood_order.nfce_invoice_id

    row = apply_marketplace_logistic_sync(
        tenant=tenant_a,
        provider="ifood",
        payload={"external_order_id": "CAN-100", "cancelled": True},
    )
    assert row["action"] == "cancelled"
    assert row["requires_manual_nfce_cancel"] is True

    ifood_order.refresh_from_db()
    assert ifood_order.status == FoodOrder.Status.CANCELLED
    assert ifood_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert ifood_order.nfce_invoice_id == nfce_id
    codes = {w["code"] for w in ifood_order.fiscal_warnings or []}
    assert "marketplace_cancelled_with_nfce" in codes


@pytest.mark.django_db
def test_sync_stub_cancel_event(tenant_a, product, settings):
    settings.MARKETPLACE_HTTP_MODE = "stub"
    conn = upsert_marketplace_connection(
        tenant=tenant_a,
        provider="ifood",
        merchant_ref="loja-cancel",
        settings={
            "http_mode": "stub",
            "stub_orders": [
                {
                    "external_order_id": "STUB-CAN-1",
                    "customer_name": "Buyer",
                    "lines": [{"sku": "CAN-01", "quantity": "1", "unit_price_cents": 1500}],
                    "paid": True,
                },
                {"external_order_id": "STUB-CAN-1", "cancelled": True},
            ],
        },
    )
    first = sync_marketplace_connection(tenant=tenant_a, connection=conn)
    assert first["imported"] == 1

    second = sync_marketplace_connection(tenant=tenant_a, connection=conn)
    assert second["updated"] >= 1

    order = FoodOrder.objects.get(tenant=tenant_a, channel_ref="STUB-CAN-1")
    assert order.status == FoodOrder.Status.CANCELLED
    assert order.fiscal_status == FoodOrder.FiscalStatus.PENDING


@pytest.mark.django_db
def test_cancel_unknown_order_skipped(tenant_a):
    row = apply_marketplace_logistic_sync(
        tenant=tenant_a,
        provider="ifood",
        payload={"external_order_id": "UNKNOWN", "cancelled": True},
    )
    assert row["action"] == "skipped"
    assert row["code"] == "order_not_found"


@pytest.mark.django_db
def test_find_marketplace_order(tenant_a, ifood_order):
    found = find_marketplace_order(
        tenant=tenant_a, provider="ifood", external_order_id="CAN-100"
    )
    assert found.id == ifood_order.id


@pytest.mark.django_db
def test_cancel_idempotent(tenant_a, ifood_order):
    cancel_marketplace_order_logistic(tenant=tenant_a, order=ifood_order)
    ifood_order.refresh_from_db()
    again = cancel_marketplace_order_logistic(tenant=tenant_a, order=ifood_order)
    assert again.status == FoodOrder.Status.CANCELLED


@pytest.mark.django_db
def test_apply_missing_external_id(tenant_a):
    row = apply_marketplace_logistic_sync(
        tenant=tenant_a, provider="ifood", payload={"cancelled": True}
    )
    assert row["code"] == "missing_external_order_id"


@pytest.mark.django_db
def test_cancel_from_fulfilled_forces_logistic(tenant_a, ifood_order):
    ifood_order.status = FoodOrder.Status.FULFILLED
    ifood_order.save(update_fields=["status"])
    order = cancel_marketplace_order_logistic(tenant=tenant_a, order=ifood_order)
    assert order.status == FoodOrder.Status.CANCELLED


@pytest.mark.django_db
def test_find_marketplace_order_empty_ref(tenant_a):
    assert find_marketplace_order(tenant=tenant_a, provider="ifood", external_order_id="") is None


@pytest.mark.django_db
def test_hp_07_delivered_does_not_change_fiscal(tenant_a, ifood_order):
    """Evento logístico entregue não altera fiscal_status."""
    ifood_order.fiscal_status = FoodOrder.FiscalStatus.PENDING
    ifood_order.status = FoodOrder.Status.FULFILLED
    ifood_order.save(update_fields=["status", "fiscal_status"])

    row = apply_marketplace_logistic_sync(
        tenant=tenant_a,
        provider="ifood",
        payload={"external_order_id": "CAN-100", "cancelled": False},
    )
    assert row["code"] == "not_cancelled"
    ifood_order.refresh_from_db()
    assert ifood_order.fiscal_status == FoodOrder.FiscalStatus.PENDING
