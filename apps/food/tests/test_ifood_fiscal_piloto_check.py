"""Checklist e KPIs piloto produção iFood × NFC-e."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.accounts.tenant_emission import apply_emission_flags
from apps.food.fiscal.metrics import compute_ifood_fiscal_piloto_kpis
from apps.food.fiscal.piloto_check import run_ifood_fiscal_piloto_checks
from apps.food.models import FoodMarketplaceConnection
from apps.food.operations import import_marketplace_order
from apps.food.services import create_food_product
from apps.master_data.models import Provider, TaxRegime
from apps.nfe.services import create_product


@pytest.fixture
def piloto_lab_settings(settings, tenant_a):
    settings.DEBUG = True
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    settings.MARKETPLACE_HTTP_MODE = "stub"
    settings.FIELD_ENCRYPTION_KEY = "n_AQ8FIJHEVdMys3lkm17BygqS8UkBCEfRtzlNaZhhw="
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
        legal_name="EXEQ FOOD PILOT",
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
def piloto_ready(tenant_a, piloto_lab_settings, provider_sp):
    nfe = create_product(
        tenant=tenant_a,
        code="PILOT-SKU",
        description="Item piloto",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    food = create_food_product(
        tenant=tenant_a,
        sku="PILOT-SKU",
        name="Prato piloto",
        price_cents=1500,
        cost_cents=800,
        unit="un",
        initial_stock=Decimal("20"),
    )
    food.nfe_product = nfe
    food.save(update_fields=["nfe_product"])
    conn = FoodMarketplaceConnection.objects.create(
        tenant=tenant_a,
        provider=FoodMarketplaceConnection.Provider.IFOOD,
        merchant_ref="merchant-pilot",
        is_active=True,
        settings={"stub_orders": [{"id": "stub-1"}]},
    )
    order = import_marketplace_order(
        tenant=tenant_a,
        provider="ifood",
        external_order_id="PILOT-001",
        customer_name="Cliente piloto",
        customer_phone="+5511955554444",
        lines=[{"sku": food.sku, "quantity": "1", "unit_price_cents": 1500}],
        paid=True,
    )
    order.customer.document = "39053344705"
    order.customer.save(update_fields=["document"])
    return {"conn": conn, "order": order}


@pytest.mark.django_db
def test_compute_ifood_fiscal_piloto_kpis(piloto_ready, tenant_a):
    kpis = compute_ifood_fiscal_piloto_kpis(tenant_id=tenant_a.id)
    assert kpis["orders_imported"] >= 1
    assert "fiscal_by_status" in kpis
    assert kpis["audit_events"] >= 0


@pytest.mark.django_db
def test_piloto_check_lab_ready(piloto_ready, tenant_a):
    report = run_ifood_fiscal_piloto_checks(tenant=tenant_a, strict_prod=False)
    by_id = {c["id"]: c for c in report["checks"]}
    assert by_id["PILOT-03-NFCE-GLOBAL"]["ok"]
    assert by_id["PILOT-05-TENANT-NFCE"]["ok"]
    assert by_id["PILOT-07-PROVIDER"]["ok"]
    assert by_id["PILOT-09-IFOOD-CONNECTION"]["ok"]
    assert by_id["PILOT-11-PRODUCT-MAP"]["ok"]
    assert by_id["PILOT-12-BEAT-SYNC"]["ok"]
    assert by_id["PILOT-13-BEAT-RECONCILE"]["ok"]
    assert by_id["PILOT-14-BEAT-NFCE"]["ok"]
    assert report["ready_for_pilot"] is True
    assert report["kpis_7d"]["orders_imported"] >= 1


@pytest.mark.django_db
def test_piloto_check_strict_prod_fails_lab(piloto_ready, tenant_a, piloto_lab_settings):
    report = run_ifood_fiscal_piloto_checks(tenant=tenant_a, strict_prod=True)
    assert report["ready_for_pilot"] is False
    by_id = {c["id"]: c for c in report["checks"]}
    assert not by_id["PILOT-01-DEBUG"]["ok"]
    assert not by_id["PILOT-02-CELERY-EAGER"]["ok"]


@pytest.mark.django_db
def test_ifood_fiscal_piloto_check_command(piloto_ready, tenant_a, tmp_path):
    out = tmp_path / "piloto_check.json"
    call_command(
        "ifood_fiscal_piloto_check",
        "--tenant",
        tenant_a.slug,
        "--out",
        str(out),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ready_for_pilot"] is True
    assert data["tenant_slug"] == tenant_a.slug


@pytest.mark.django_db
def test_ifood_fiscal_piloto_evidence_command(piloto_ready, tenant_a, tmp_path):
    out = tmp_path / "piloto_evidence.json"
    call_command(
        "ifood_fiscal_piloto_evidence",
        "--tenant",
        tenant_a.slug,
        "--out",
        str(out),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["checklist"]["ready_for_pilot"] is True
    assert "food.reconcile_ifood_fiscal" in str(data["celery_beat"])
    assert data["kpis"]["orders_imported"] >= 1


@pytest.mark.django_db
def test_nfce_reconcile_stale_task(settings):
    from apps.nfce.tasks import reconcile_stale_nfce_task

    stats = reconcile_stale_nfce_task(limit=5)
    assert isinstance(stats, dict)
