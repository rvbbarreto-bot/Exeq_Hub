"""EX-SEC — segurança fiscal iFood (B9)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.models import TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.emit import emit_food_orders_batch
from apps.food.models import FoodOrder
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.food.tasks import emit_food_ifood_batch_task
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
def tenant_a_order(tenant_a, nfce_settings, provider_sp):
    nfe = create_product(
        tenant=tenant_a,
        code="SEC-01",
        description="Item SEC",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="SEC-SKU",
        name="Prato SEC",
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
        external_order_id="SEC-ORDER",
        customer_name="Cliente SEC",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return order


def _login(api_client, tenant, email, password="Secret123!"):
    return api_client.post(
        "/api/v1/auth/login",
        {"tenant_slug": tenant.slug, "email": email, "password": password},
        format="json",
    )


@pytest.mark.django_db
def test_ex_sec_01_cross_tenant_emit_blocked(
    api_client, tenant_a, tenant_b, tenant_a_order, roles
):
    """EX-SEC-01 / EX-EMT-10: tenant B não emite pedido do tenant A."""
    user_b = User.objects.create_user(
        email="sec-b@exeq.local", password="Secret123!", name="Sec B"
    )
    TenantMembership.objects.create(
        tenant=tenant_b, user=user_b, role=roles["tenant_admin"], is_active=True
    )
    login = _login(api_client, tenant_b, user_b.email)
    assert login.status_code == 200
    header_b = {"HTTP_AUTHORIZATION": f"Bearer {login.data['access']}"}

    emit = api_client.post(
        "/api/v1/food/ifood/emit-batch/",
        {"order_ids": [str(tenant_a_order.id)], "async": False},
        format="json",
        **header_b,
    )
    assert emit.status_code == 400
    tenant_a_order.refresh_from_db()
    assert tenant_a_order.fiscal_status != FoodOrder.FiscalStatus.AUTHORIZED


@pytest.mark.django_db
def test_ex_sec_02_worker_wrong_tenant(tenant_a, tenant_b, tenant_a_order):
    """EX-SEC-02: task Celery com tenant errado não emite pedido alheio."""
    result = emit_food_ifood_batch_task(
        str(tenant_b.id),
        [str(tenant_a_order.id)],
        actor="celery-test",
    )
    assert result.get("rejected_cross_tenant") == 1
    assert result.get("authorized", 0) == 0
    tenant_a_order.refresh_from_db()
    assert tenant_a_order.fiscal_status != FoodOrder.FiscalStatus.AUTHORIZED


@pytest.mark.django_db
def test_ex_sec_05_readonly_cannot_emit(
    api_client, tenant_a, tenant_a_order, roles
):
    """EX-SEC-05: readonly recebe 403 ao emitir lote."""
    user_ro = User.objects.create_user(
        email="sec-ro@exeq.local", password="Secret123!", name="Readonly"
    )
    TenantMembership.objects.create(
        tenant=tenant_a, user=user_ro, role=roles["readonly"], is_active=True
    )
    login = _login(api_client, tenant_a, user_ro.email)
    assert login.status_code == 200
    header_ro = {"HTTP_AUTHORIZATION": f"Bearer {login.data['access']}"}

    emit = api_client.post(
        "/api/v1/food/ifood/emit-batch/",
        {"order_ids": [str(tenant_a_order.id)], "async": False},
        format="json",
        **header_ro,
    )
    assert emit.status_code == 403


@pytest.mark.django_db
def test_emit_batch_scoped_to_tenant(
    tenant_a, tenant_b, tenant_a_order, nfce_settings, provider_sp, settings
):
    """EX-EMT-10: serviço não emite pedido de outro tenant."""
    settings.NFE_ENABLED = True
    tenant_b.settings = apply_emission_flags(
        tenant_b.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_b.save(update_fields=["settings", "updated_at"])
    nfe = create_product(
        tenant=tenant_b,
        code="SEC-B",
        description="B",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    food_b = create_food_product(
        tenant=tenant_b,
        sku="SEC-B-SKU",
        name="B",
        price_cents=1000,
        cost_cents=400,
        unit="un",
        initial_stock=Decimal("5"),
    )
    food_b.nfe_product = nfe
    food_b.save(update_fields=["nfe_product"])
    order_b = import_marketplace_order(
        tenant=tenant_b,
        provider="ifood",
        external_order_id="SEC-B-ORDER",
        customer_name="B",
        customer_phone="+5511944443333",
        lines=[{"sku": food_b.sku, "quantity": "1", "unit_price_cents": 1000}],
        paid=True,
    )

    result = emit_food_orders_batch(
        tenant=tenant_a,
        order_ids=[tenant_a_order.id, order_b.id],
        actor="test",
    )
    assert result["authorized"] == 1
    assert result["failed"] == 1
    tenant_a_order.refresh_from_db()
    order_b.refresh_from_db()
    assert tenant_a_order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
    assert order_b.fiscal_status != FoodOrder.FiscalStatus.AUTHORIZED
