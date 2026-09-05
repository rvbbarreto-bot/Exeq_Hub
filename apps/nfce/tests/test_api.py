"""API REST NFC-e — gate, checkout, emit."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.tenant_emission import apply_emission_flags
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfe.services import create_product


@pytest.fixture
def nfce_api(settings, tenant_a):
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
        legal_name="EXEQ PDV API",
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


@pytest.mark.django_db
def test_gate_and_checkout(api_client, auth_header, nfce_api, tenant_a, provider_sp):
    gate = api_client.get("/api/v1/nfce/gate/", **auth_header)
    assert gate.status_code == 200
    assert gate.data["enabled"] is True
    assert gate.data["can_create"] is True

    product = create_product(
        tenant=tenant_a,
        code="API1",
        description="Item API",
        ncm="21069090",
        unit_price_cents=2500,
        csosn="102",
    )

    preview = api_client.post(
        "/api/v1/nfce/policy/preview",
        {
            "provider_id": str(provider_sp.id),
            "total_cents": 5000,
        },
        format="json",
        **auth_header,
    )
    assert preview.status_code == 200
    assert preview.data["model"] == "65"
    assert preview.data["omit_dest"] is True

    checkout = api_client.post(
        "/api/v1/nfce/checkout",
        {
            "idempotency_key": "api-nfce-1",
            "provider_id": str(provider_sp.id),
            "items": [{"product_id": str(product.id), "quantity": "2"}],
        },
        format="json",
        **auth_header,
    )
    assert checkout.status_code == 202, checkout.data
    assert checkout.data["status"] == "authorized"
    assert len(checkout.data["access_key"]) == 44

    xml = api_client.get(
        f"/api/v1/nfce/invoices/{checkout.data['id']}/artifacts/xml",
        **auth_header,
    )
    assert xml.status_code == 200
    assert b"<mod>65</mod>" in xml.content


@pytest.mark.django_db
def test_cancel_api(api_client, auth_header, nfce_api, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="CANAPI",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    checkout = api_client.post(
        "/api/v1/nfce/checkout",
        {
            "idempotency_key": "api-cancel-1",
            "provider_id": str(provider_sp.id),
            "items": [{"product_id": str(product.id), "quantity": "1"}],
        },
        format="json",
        **auth_header,
    )
    inv_id = checkout.data["id"]
    cancel = api_client.post(
        f"/api/v1/nfce/invoices/{inv_id}/cancel",
        {"justificativa": "Cancelamento via API teste homolog"},
        format="json",
        **auth_header,
    )
    assert cancel.status_code == 200
    assert cancel.data["status"] == "cancelled"
    assert "cancel" not in cancel.data["allowed_actions"]


@pytest.mark.django_db
def test_checkout_cnpj_returns_409(api_client, auth_header, nfce_api, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="B2B",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    r = api_client.post(
        "/api/v1/nfce/checkout",
        {
            "idempotency_key": "api-cnpj",
            "provider_id": str(provider_sp.id),
            "items": [{"product_id": str(product.id), "quantity": "1"}],
            "cnpj": "37229907000137",
        },
        format="json",
        **auth_header,
    )
    assert r.status_code == 409
    assert r.data["route"] == "nfe"
    assert NfceInvoice.objects.filter(tenant=tenant_a).count() == 0
