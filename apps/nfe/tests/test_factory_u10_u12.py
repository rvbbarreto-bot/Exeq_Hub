"""U10–U12 — OpenAPI merge, imutabilidade pós-emit, helpers de gate."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.exceptions import NfeDisabledError, NfeInvalidTransitionError
from apps.nfe.models import NfeInvoice
from apps.nfe.services import (
    create_draft,
    create_product,
    emit_invoice,
    is_content_locked,
    is_snapshot_frozen,
    replace_items,
    require_content_mutable,
    require_nfe_enabled,
    validate_invoice,
)
from apps.ops.openapi_views import load_openapi_dict


NFE_REQUIRED_PATHS = (
    "/nfe/gate/",
    "/nfe/config/",
    "/nfe/products/",
    "/nfe/invoices/",
    "/nfe/invoices/{id}/",
    "/nfe/invoices/{id}/items",
    "/nfe/invoices/{id}/emit",
    "/nfe/invoices/{id}/events",
    "/nfe/invoices/{id}/artifacts/xml",
    "/nfe/invoices/{id}/artifacts/pdf",
)


def test_openapi_includes_nfe_paths():
    load_openapi_dict.cache_clear()
    spec = load_openapi_dict()
    paths = spec["paths"]
    for p in NFE_REQUIRED_PATHS:
        assert p in paths, f"missing {p}"
    schemas = (spec.get("components") or {}).get("schemas") or {}
    assert "NfeInvoice" in schemas
    assert "NfeGate" in schemas
    tag_names = {
        t.get("name") if isinstance(t, dict) else t for t in (spec.get("tags") or [])
    }
    assert "nfe" in tag_names
    load_openapi_dict.cache_clear()


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


def _emit_stub(tenant, provider, customer, key="u11-immut"):
    product = create_product(
        tenant=tenant,
        code="IM1",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key=key,
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    return emit_invoice(inv)


@pytest.mark.django_db
def test_authorized_is_immutable(nfe_settings, tenant_a, provider_sp, customer_b2b):
    inv = _emit_stub(tenant_a, provider_sp, customer_b2b)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert is_content_locked(inv) is True
    assert is_snapshot_frozen(inv) is True
    with pytest.raises(NfeInvalidTransitionError, match="imutável"):
        require_content_mutable(inv)
    with pytest.raises(NfeInvalidTransitionError):
        replace_items(inv, items=[{"code": "X", "description": "Y", "ncm": "21069090", "quantity": "1", "unit_price_cents": 1, "csosn": "102"}])
    with pytest.raises(NfeInvalidTransitionError):
        validate_invoice(inv)


@pytest.mark.django_db
def test_feature_flag_off_blocks_domain(settings, tenant_a, provider_sp, customer_b2b):
    settings.NFE_ENABLED = False
    with pytest.raises(NfeDisabledError):
        require_nfe_enabled()
    with pytest.raises(NfeDisabledError):
        create_draft(
            tenant=tenant_a,
            provider=provider_sp,
            customer=customer_b2b,
            idempotency_key="flag-off",
        )


@pytest.mark.django_db
def test_openapi_json_endpoint_has_nfe(api_client):
    load_openapi_dict.cache_clear()
    r = api_client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert "/nfe/gate/" in r.data["paths"]
    load_openapi_dict.cache_clear()


@pytest.mark.django_db
def test_gate_api_when_flag_off(tenant_a, provider_sp, auth_header, api_client, settings):
    settings.NFE_ENABLED = False
    r = api_client.get(reverse("nfe-gate"), **auth_header)
    assert r.status_code == 200
    assert r.data["enabled"] is False
    assert r.data["can_create"] is False
