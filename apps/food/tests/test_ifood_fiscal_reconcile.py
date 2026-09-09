"""EX-EMT-05/07 — reconcile PROCESSING e timeout SEFAZ (B5)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_order_nfce, emit_food_orders_batch
from apps.food.fiscal.reconcile import reconcile_stale_food_fiscal_processing
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfce.polling import poll_nfce_invoice
from apps.nfe.services import create_product
from integrations.sefaz_nfe.port import NfeEmitResult, StubNfeProvider


@pytest.fixture
def nfce_settings(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    settings.FOOD_FISCAL_RECONCILE_STALE_SECONDS = 60
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
        code="REC-01",
        description="Item REC",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="REC-SKU",
        name="Prato REC",
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
        external_order_id="REC-ORDER",
        customer_name="Cliente REC",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


class PollingEmitStub(StubNfeProvider):
    def emitir(self, *, invoice_snapshot, context=None):
        base = super().emitir(invoice_snapshot=invoice_snapshot, context=context)
        return NfeEmitResult(
            status="polling",
            access_key=base.access_key,
            protocol=base.protocol,
            rejection_code="103",
            rejection_message="Lote recebido",
            raw={"mode": "stub", "nRec": "999888777666555"},
        )

    def consultar(self, *, access_key="", receipt="", tp_amb="2", context=None):
        return NfeEmitResult(
            status="authorized",
            access_key=access_key,
            protocol="STUBPOLL777",
        )


@pytest.mark.django_db
def test_ex_emt_07_polling_then_authorized_no_duplicate(
    tenant_a, ready_order, provider_sp
):
    """EX-EMT-07: timeout/polling → consulta autoriza — zero duplicata."""
    with patch("apps.nfce.services.get_nfce_provider", return_value=PollingEmitStub()):
        with patch("apps.nfce.polling.schedule_nfce_poll"):
            first = emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="t1")
    ready_order.refresh_from_db()
    assert ready_order.fiscal_status == FoodOrder.FiscalStatus.PROCESSING
    assert ready_order.nfce_invoice_id is not None
    assert first["status"] == FoodOrder.FiscalStatus.PROCESSING

    with patch("apps.nfce.services.get_nfce_provider", return_value=PollingEmitStub()):
        second = emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="t2")
    assert second["status"] == "skipped"
    assert second["reason"] in {"processing", "already_authorized"}

    inv = ready_order.nfce_invoice
    with patch("apps.nfce.polling.get_nfce_provider", return_value=PollingEmitStub()):
        poll_nfce_invoice(inv, actor="test_poll")

    ready_order.refresh_from_db()
    assert ready_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert (
        NfceInvoice.objects.filter(
            tenant=tenant_a,
            idempotency_key=f"food:ifood:{ready_order.id}",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_ex_emt_05_reconcile_stale_processing(tenant_a, ready_order, provider_sp):
    """EX-EMT-05: worker morre em PROCESSING — reconcile consulta emissor."""
    with patch("apps.nfce.services.get_nfce_provider", return_value=PollingEmitStub()):
        with patch("apps.nfce.polling.schedule_nfce_poll"):
            emit_food_order_nfce(tenant=tenant_a, order_id=ready_order.id, actor="worker")

    ready_order.refresh_from_db()
    assert ready_order.fiscal_status == FoodOrder.FiscalStatus.PROCESSING
    stale = timezone.now() - timedelta(seconds=120)
    FoodOrder.objects.filter(pk=ready_order.pk).update(updated_at=stale)

    with patch("apps.nfce.polling.get_nfce_provider", return_value=PollingEmitStub()):
        stats = reconcile_stale_food_fiscal_processing(limit=10)

    assert stats["checked"] >= 1
    ready_order.refresh_from_db()
    assert ready_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED


@pytest.mark.django_db
def test_ex_emt_06_sefaz_reject_via_batch(tenant_a, ready_order, provider_sp, monkeypatch):
    """EX-EMT-06 / HP-05: rejeição SEFAZ persiste código e mensagem."""
    import uuid

    from apps.nfce.services import create_draft

    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        idempotency_key=f"food:ifood:{ready_order.id}",
        omit_dest=True,
    )
    inv.status = NfceInvoice.Status.REJECTED
    inv.rejection_code = "573"
    inv.rejection_message = "Rejeição SEFAZ teste"
    inv.save(
        update_fields=["status", "rejection_code", "rejection_message", "updated_at"]
    )

    monkeypatch.setattr(
        "apps.food.fiscal.emit.checkout_and_emit_nfce", lambda **kw: inv
    )
    result = emit_food_orders_batch(
        tenant=tenant_a,
        order_ids=[ready_order.id],
        actor="test",
    )
    assert result["failed"] == 1
    ready_order.refresh_from_db()
    assert ready_order.fiscal_status == FoodOrder.FiscalStatus.REJECTED
    assert ready_order.fiscal_rejection_code == "573"
    assert "SEFAZ" in ready_order.fiscal_rejection_message
