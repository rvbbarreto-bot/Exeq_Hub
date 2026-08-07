"""U20–U22 — attempts RF-44 · catalog lite · gate checks · flags API."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.catalog import CATALOG_VERSION, validate_ncm
from apps.nfe.models import NfeInvoice, NfeTransmissionAttempt
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
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
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av T",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_emit_records_transmission_attempt(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    product = create_product(
        tenant=tenant_a,
        code="U20A",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u20-attempt",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv = emit_invoice(inv)
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    att = NfeTransmissionAttempt.objects.filter(tenant=tenant_a, invoice=inv, stage="emit").first()
    assert att is not None
    assert att.result_status == "authorized"
    assert att.correlation_id == inv.correlation_id
    assert inv.fiscal_snapshot.get("catalog_version") == CATALOG_VERSION


@pytest.mark.django_db
def test_attempts_api(nfe_settings, tenant_a, provider_sp, customer_b2b, api_client, auth_header):
    product = create_product(
        tenant=tenant_a, code="U20B", description="X", ncm="21069090", unit_price_cents=500
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u20-api",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv = emit_invoice(inv)
    r = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/attempts", **auth_header)
    assert r.status_code == 200
    assert len(r.data["attempts"]) >= 1
    assert r.data["attempts"][0]["stage"] == "emit"


@pytest.mark.django_db
def test_flags_and_gate_ibge(
    nfe_settings, tenant_a, provider_sp, customer_b2b, api_client, auth_header
):
    product = create_product(
        tenant=tenant_a, code="U20C", description="Y", ncm="21069090", unit_price_cents=500
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u20-flags",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv = emit_invoice(inv)
    inv.last_validation = {"denegada": True, "pdf_pending": False}
    inv.save(update_fields=["last_validation", "updated_at"])
    r = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/", **auth_header)
    assert r.status_code == 200
    assert r.data["flags"]["denegada"] is True

    g = api_client.get("/api/v1/nfe/gate/", **auth_header)
    assert g.status_code == 200
    ids = {c["id"] for c in g.data["checks"]}
    assert "ibge_emit" in ids
    assert "crt" in ids
    assert "uf_supported" in ids


def test_catalog_ncm():
    assert validate_ncm("21069090") is None
    assert validate_ncm("00000000") is not None


@pytest.mark.django_db
def test_catalog_blocks_unknown_ncm_in_http(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    from apps.nfe.tax import build_validation

    product = create_product(
        tenant=tenant_a,
        code="BAD-NCM",
        description="X",
        ncm="99999999",
        unit_price_cents=100,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u20-ncm-bad",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    inv.items.update(ncm="99999999")
    # catalog enforce only with require_ie=True (http path)
    ok_stub = build_validation(inv, require_ie=False)
    assert ok_stub["ok"] is True or not any(
        "catálogo" in e["message"] for e in ok_stub["field_errors"]
    )
    result = build_validation(inv, require_ie=True)
    assert result["ok"] is False
    assert any("catálogo" in e["message"] or "NCM" in e["message"] for e in result["field_errors"])
