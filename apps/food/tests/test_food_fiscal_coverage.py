"""Testes cobertura apps.food.fiscal — ident, adapter, readiness edge cases."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.exceptions import FoodInvalidOrderError
from apps.food.fiscal.adapter import (
    build_nfce_items_from_food_order,
    food_order_delivery_flag,
)
from apps.food.fiscal.ident import resolve_food_order_customer_ident
from apps.food.fiscal.mapping import (
    order_lines_mapping_summary,
    refresh_ifood_orders_for_food_product,
)
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness, resolve_emit_provider
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfe.models import NfeProduct


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
def ifood_order(tenant_a):
    food = create_food_product(
        tenant=tenant_a,
        sku="COV-SKU",
        name="Cov",
        price_cents=1000,
        cost_cents=500,
        unit="un",
        initial_stock=Decimal("5"),
    )
    nfe = NfeProduct.objects.create(
        tenant=tenant_a,
        code="COV-NFE",
        description="NFE",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    food.nfe_product = nfe
    food.save(update_fields=["nfe_product"])
    return import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="COV-1",
        customer_name="C",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1000}],
        paid=True,
    )


@pytest.mark.django_db
def test_ident_cpf_and_cnpj(ifood_order):
    ifood_order.customer.document = "39053344705"
    ifood_order.customer.save(update_fields=["document"])
    cpf, cnpj = resolve_food_order_customer_ident(ifood_order)
    assert cpf == "39053344705"
    assert cnpj is None

    ifood_order.customer.document = "00000000000191"
    ifood_order.customer.save(update_fields=["document"])
    cpf, cnpj = resolve_food_order_customer_ident(ifood_order)
    assert cpf is None
    assert cnpj == "00000000000191"


@pytest.mark.django_db
def test_ident_empty(ifood_order):
    ifood_order.customer.document = ""
    ifood_order.customer.save(update_fields=["document"])
    cpf, cnpj = resolve_food_order_customer_ident(ifood_order)
    assert cpf is None and cnpj is None


@pytest.mark.django_db
def test_adapter_delivery_flag(ifood_order):
    assert food_order_delivery_flag(ifood_order) is True
    ifood_order.fulfillment_mode = FoodOrder.FulfillmentMode.PICKUP
    ifood_order.save(update_fields=["fulfillment_mode"])
    assert food_order_delivery_flag(ifood_order) is False


@pytest.mark.django_db
def test_adapter_rejects_non_ifood(ifood_order):
    ifood_order.channel = FoodOrder.Channel.COUNTER
    ifood_order.save(update_fields=["channel"])
    with pytest.raises(FoodInvalidOrderError, match="ifood"):
        build_nfce_items_from_food_order(ifood_order)


@pytest.mark.django_db
def test_adapter_rejects_unmapped(ifood_order):
    line = ifood_order.lines.select_related("product").first()
    line.product.nfe_product = None
    line.product.save(update_fields=["nfe_product"])
    with pytest.raises(FoodInvalidOrderError, match="mapeado"):
        build_nfce_items_from_food_order(ifood_order)


@pytest.mark.django_db
def test_readiness_non_ifood_returns_empty(tenant_a, ifood_order):
    ifood_order.channel = FoodOrder.Channel.COUNTER
    ifood_order.save(update_fields=["channel"])
    assert assess_food_order_fiscal_readiness(ifood_order) == []


@pytest.mark.django_db
def test_readiness_delivery_without_ident(ifood_order):
    ifood_order.customer.document = ""
    ifood_order.customer.save(update_fields=["document"])
    codes = {w["code"] for w in assess_food_order_fiscal_readiness(ifood_order)}
    assert "delivery_requires_identification" in codes


@pytest.mark.django_db
def test_resolve_emit_provider_from_connection(tenant_a, provider_sp, ifood_order):
    from apps.food.models import FoodMarketplaceConnection

    conn = FoodMarketplaceConnection.objects.create(
        tenant=tenant_a,
        provider="ifood",
        merchant_ref="loja-x",
        settings={"provider_id": str(provider_sp.id)},
    )
    ifood_order.marketplace_connection = conn
    ifood_order.save(update_fields=["marketplace_connection"])
    assert resolve_emit_provider(tenant=tenant_a, order=ifood_order).id == provider_sp.id


@pytest.mark.django_db
def test_refresh_ifood_orders_for_product_skips_authorized(
    tenant_a, ifood_order, nfce_settings, provider_sp
):
    from apps.food.fiscal.emit import emit_food_orders_batch

    ifood_order.customer.document = "39053344705"
    ifood_order.customer.save(update_fields=["document"])
    emit_food_orders_batch(tenant=tenant_a, order_ids=[ifood_order.id], actor="t")
    ifood_order.refresh_from_db()
    product = ifood_order.lines.first().product
    count = refresh_ifood_orders_for_food_product(tenant=tenant_a, product=product)
    assert count == 0


@pytest.mark.django_db
def test_order_lines_mapping_summary(ifood_order):
    summary = order_lines_mapping_summary(ifood_order)
    assert summary["all_mapped"] is True
    assert summary["line_count"] == 1


@pytest.mark.django_db
def test_mapping_invalid_nfe_product(tenant_a, ifood_order):
    product = ifood_order.lines.first().product
    with pytest.raises(FoodInvalidOrderError, match="fiscal"):
        from apps.food.fiscal.mapping import set_food_product_nfe_mapping

        set_food_product_nfe_mapping(
            tenant=tenant_a,
            product=product,
            nfe_product_id="00000000-0000-0000-0000-000000000099",
        )


@pytest.mark.django_db
def test_mapping_unmap_product(tenant_a, ifood_order):
    from apps.food.fiscal.mapping import set_food_product_nfe_mapping

    product = ifood_order.lines.first().product
    count_before = order_lines_mapping_summary(ifood_order)["all_mapped"]
    assert count_before is True
    set_food_product_nfe_mapping(tenant=tenant_a, product=product, nfe_product_id=None)
    product.refresh_from_db()
    assert product.nfe_product_id is None


@pytest.mark.django_db
def test_is_food_order_not_ready_non_ifood(ifood_order):
    from apps.food.fiscal.mapping import is_food_order_fiscally_ready

    ifood_order.channel = FoodOrder.Channel.COUNTER
    ifood_order.save(update_fields=["channel"])
    assert is_food_order_fiscally_ready(ifood_order) is False


@pytest.mark.django_db
def test_refresh_food_order_skips_non_ifood(ifood_order):
    from apps.food.fiscal.readiness import refresh_food_order_fiscal_state

    ifood_order.channel = FoodOrder.Channel.COUNTER
    ifood_order.fiscal_status = ""
    ifood_order.save(update_fields=["channel", "fiscal_status"])
    refresh_food_order_fiscal_state(ifood_order)
    ifood_order.refresh_from_db()
    assert ifood_order.fiscal_status == ""


@pytest.mark.django_db
def test_readiness_inactive_nfe_product(ifood_order):
    nfe = ifood_order.lines.first().product.nfe_product
    nfe.is_active = False
    nfe.save(update_fields=["is_active"])
    codes = {w["code"] for w in assess_food_order_fiscal_readiness(ifood_order)}
    assert "nfe_product_inactive" in codes


@pytest.mark.django_db
def test_readiness_nfce_disabled_global(ifood_order, settings):
    settings.NFCE_ENABLED = False
    codes = {w["code"] for w in assess_food_order_fiscal_readiness(ifood_order)}
    assert "nfce_disabled_global" in codes


@pytest.mark.django_db
def test_readiness_cancelled_with_authorized(ifood_order):
    ifood_order.fiscal_status = FoodOrder.FiscalStatus.AUTHORIZED
    ifood_order.status = FoodOrder.Status.CANCELLED
    ifood_order.save(update_fields=["fiscal_status", "status"])
    codes = {w["code"] for w in assess_food_order_fiscal_readiness(ifood_order)}
    assert "marketplace_cancelled_with_nfce" in codes


@pytest.mark.django_db
def test_emit_skip_not_ifood(tenant_a, ifood_order):
    from apps.food.fiscal.emit import emit_food_order_nfce

    ifood_order.channel = FoodOrder.Channel.WHATSAPP
    ifood_order.save(update_fields=["channel"])
    result = emit_food_order_nfce(tenant=tenant_a, order_id=ifood_order.id)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_ifood_channel"


@pytest.mark.django_db
def test_emit_skip_processing(tenant_a, ifood_order):
    from apps.food.fiscal.emit import emit_food_order_nfce

    ifood_order.fiscal_status = FoodOrder.FiscalStatus.PROCESSING
    ifood_order.save(update_fields=["fiscal_status"])
    result = emit_food_order_nfce(tenant=tenant_a, order_id=ifood_order.id)
    assert result["reason"] == "processing"


@pytest.mark.django_db
def test_emit_skip_cancelled_fiscal(tenant_a, ifood_order):
    from apps.food.fiscal.emit import emit_food_orders_batch

    ifood_order.fiscal_status = FoodOrder.FiscalStatus.CANCELLED
    ifood_order.save(update_fields=["fiscal_status"])
    result = emit_food_orders_batch(tenant=tenant_a, order_ids=[ifood_order.id])
    assert result["skipped"] == 1


@pytest.mark.django_db
def test_emit_no_provider(tenant_a, ifood_order, nfce_settings):
    from apps.food.fiscal.emit import emit_food_order_nfce

    ifood_order.customer.document = "39053344705"
    ifood_order.customer.save(update_fields=["document"])
    result = emit_food_order_nfce(tenant=tenant_a, order_id=ifood_order.id)
    assert result["status"] == "failed"
    assert result["code"] == "no_provider"


@pytest.mark.django_db
def test_emit_batch_order_not_found(tenant_a):
    from apps.food.fiscal.emit import emit_food_orders_batch

    result = emit_food_orders_batch(
        tenant=tenant_a,
        order_ids=["00000000-0000-0000-0000-000000000099"],
    )
    assert result["failed"] == 1
    assert result["results"][0]["code"] == "not_found"


@pytest.mark.django_db
def test_emit_order_not_found_raises(tenant_a):
    from apps.food.exceptions import FoodOrderNotFoundError
    from apps.food.fiscal.emit import emit_food_order_nfce

    with pytest.raises(FoodOrderNotFoundError):
        emit_food_order_nfce(
            tenant=tenant_a,
            order_id="00000000-0000-0000-0000-000000000099",
        )


@pytest.mark.django_db
def test_emit_policy_nfe_route(
    tenant_a, ifood_order, nfce_settings, provider_sp, monkeypatch
):
    from apps.food.fiscal.emit import emit_food_order_nfce

    ifood_order.customer.document = "39053344705"
    ifood_order.customer.save(update_fields=["document"])

    def _fake_checkout(**kwargs):
        return {"route": "nfe", "model": "55", "reasons": ["cnpj"]}

    monkeypatch.setattr("apps.food.fiscal.emit.checkout_and_emit_nfce", _fake_checkout)
    result = emit_food_order_nfce(tenant=tenant_a, order_id=ifood_order.id)
    assert result["code"] == "policy_nfe"


@pytest.mark.django_db
def test_emit_nfce_domain_error(
    tenant_a, ifood_order, nfce_settings, provider_sp, monkeypatch
):
    from apps.food.fiscal.emit import emit_food_order_nfce
    from apps.nfce.exceptions import NfceGateError

    ifood_order.customer.document = "39053344705"
    ifood_order.customer.save(update_fields=["document"])

    def _raise(**kwargs):
        raise NfceGateError("gate bloqueado")

    monkeypatch.setattr("apps.food.fiscal.emit.checkout_and_emit_nfce", _raise)
    result = emit_food_order_nfce(tenant=tenant_a, order_id=ifood_order.id)
    assert result["status"] == "failed"
    assert result["code"] == "nfce_gate"


@pytest.mark.django_db
def test_emit_rejected_invoice_mapping(
    tenant_a, ifood_order, nfce_settings, provider_sp, monkeypatch
):
    import uuid

    from apps.food.fiscal.emit import emit_food_order_nfce
    from apps.nfce.models import NfceInvoice
    from apps.nfce.services import create_draft

    ifood_order.customer.document = "39053344705"
    ifood_order.customer.save(update_fields=["document"])

    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        idempotency_key=f"test-rej-{uuid.uuid4()}",
        omit_dest=True,
    )
    inv.status = NfceInvoice.Status.REJECTED
    inv.rejection_code = "573"
    inv.rejection_message = "SEFAZ rejeitou"
    inv.save(
        update_fields=["status", "rejection_code", "rejection_message", "updated_at"]
    )

    monkeypatch.setattr(
        "apps.food.fiscal.emit.checkout_and_emit_nfce", lambda **kw: inv
    )
    result = emit_food_order_nfce(tenant=tenant_a, order_id=ifood_order.id)
    assert result["status"] == "rejected"
    ifood_order.refresh_from_db()
    assert ifood_order.fiscal_rejection_code == "573"

