"""B10 — observabilidade fiscal iFood (EX-SEC-04, auditoria)."""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_order_nfce
from apps.food.fiscal.ignore import ignore_food_order_fiscal
from apps.food.fiscal.observability import (
    FISCAL_LOGGER,
    audit_food_fiscal,
    log_fiscal_event,
    sanitize_log_extra,
)
from apps.food.models import FoodFiscalEvent, FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
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
def ready_order(tenant_a, nfce_settings, provider_sp):
    nfe = create_product(
        tenant=tenant_a,
        code="OBS-01",
        description="Item OBS",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="OBS-SKU",
        name="Prato OBS",
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
        external_order_id="OBS-ORDER",
        customer_name="Cliente OBS",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


def test_sanitize_log_extra_redacts_secrets():
    """EX-SEC-04: tokens e documentos não vão crus para logs."""
    raw = sanitize_log_extra(
        {
            "authorization": "Bearer secret-token-xyz",
            "csc_token": "abc123",
            "document": "39053344705",
            "pix_copy_paste": "00020126580014br.gov.bcb.pix",
            "code": "573",
        }
    )
    assert raw["authorization"] == "[redacted]"
    assert raw["csc_token"] == "[redacted]"
    assert raw["document"] == "390***"
    assert raw["pix_copy_paste"] == "[redacted]"
    assert raw["code"] == "573"


@pytest.mark.django_db
def test_audit_food_fiscal_persists_event(tenant_a, ready_order):
    ev = audit_food_fiscal(
        tenant=tenant_a,
        order=ready_order,
        action=FoodFiscalEvent.Action.EMIT_START,
        actor="test",
        from_status=FoodOrder.FiscalStatus.PENDING,
        to_status=FoodOrder.FiscalStatus.PROCESSING,
        metadata={"token": "must-redact"},
    )
    assert ev.pk is not None
    assert ev.metadata["token"] == "[redacted]"
    assert ev.attempt == 0


@pytest.mark.django_db
def test_emit_creates_audit_trail(tenant_a, ready_order, provider_sp, caplog):
    caplog.set_level(logging.INFO, logger=FISCAL_LOGGER.name)
    emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="obs-test")
    actions = set(
        FoodFiscalEvent.objects.filter(order=ready_order).values_list("action", flat=True)
    )
    assert FoodFiscalEvent.Action.EMIT_START in actions
    assert FoodFiscalEvent.Action.EMIT_DONE in actions
    assert any("food.fiscal.emit_start" in r.message for r in caplog.records)
    assert any("tenant=" in r.message and "order=" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_ignore_creates_audit_event(tenant_a, ready_order):
    ignore_food_order_fiscal(
        tenant=tenant_a,
        order_id=ready_order.id,
        reason="Duplicidade balcão",
        actor="hub:test",
    )
    ev = FoodFiscalEvent.objects.filter(
        order=ready_order, action=FoodFiscalEvent.Action.IGNORE
    ).first()
    assert ev is not None
    assert ev.actor == "hub:test"
    assert ev.to_status == FoodOrder.FiscalStatus.IGNORED


@pytest.mark.django_db
def test_api_detail_includes_fiscal_events(
    api_client, auth_header, nfce_settings, tenant_a, provider_sp, ready_order
):
    emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="api-test")
    resp = api_client.get(
        f"/api/v1/food/ifood/fiscal/{ready_order.id}/",
        **auth_header,
    )
    assert resp.status_code == 200
    assert "fiscal_events" in resp.data
    assert len(resp.data["fiscal_events"]) >= 2
    assert resp.data["fiscal_events"][0]["action"] in {
        FoodFiscalEvent.Action.EMIT_DONE,
        FoodFiscalEvent.Action.EMIT_START,
        FoodFiscalEvent.Action.EMIT_SKIP,
    }


def test_log_fiscal_event_no_secret_in_message(caplog):
    caplog.set_level(logging.INFO, logger=FISCAL_LOGGER.name)
    log_fiscal_event(
        "test_action",
        tenant_id="t1",
        order_id="o1",
        attempt=2,
        actor="actor",
        api_token="super-secret",
    )
    joined = " ".join(r.message for r in caplog.records)
    assert "super-secret" not in joined
    assert "food.fiscal.test_action" in joined
