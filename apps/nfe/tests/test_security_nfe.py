"""EX-SEC NF-e — isolamento multi-tenant + throttle escrita (paridade NFS-e)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import TenantMembership, User
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from apps.nfe.views import NfeWriteThrottle


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


def _emit_one(tenant, provider, customer, key: str) -> NfeInvoice:
    product = create_product(
        tenant=tenant,
        code=f"SEC-{key[:6]}",
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
def test_ex_sec_01_tenant_cannot_read_other_nfe(
    api_client, auth_header, tenant_a, tenant_b, provider_sp, customer_b2b, nfe_settings, roles
):
    """EX-SEC-01: tenant B não lê NF-e/artefato do tenant A."""
    inv = _emit_one(tenant_a, provider_sp, customer_b2b, "nfe-sec-a1")
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED

    user_b = User.objects.create_user(email="bob-nfe@exeq.local", password="Secret123!", name="Bob")
    TenantMembership.objects.create(tenant=tenant_b, user=user_b, role=roles["tenant_admin"])
    login_b = api_client.post(
        "/api/v1/auth/login",
        {"tenant_slug": tenant_b.slug, "email": user_b.email, "password": "Secret123!"},
        format="json",
    )
    assert login_b.status_code == 200
    header_b = {"HTTP_AUTHORIZATION": f"Bearer {login_b.data['access']}"}

    detail = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/", **header_b)
    assert detail.status_code == 404

    listing = api_client.get("/api/v1/nfe/invoices/?days=0", **header_b)
    assert listing.status_code == 200
    rows = listing.data.get("results", listing.data)
    ids = {str(row["id"]) for row in rows}
    assert str(inv.id) not in ids

    xml = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/artifacts/xml", **header_b)
    assert xml.status_code == 404
    pdf = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/artifacts/pdf", **header_b)
    assert pdf.status_code == 404
    events = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/events", **header_b)
    assert events.status_code == 404

    own = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/", **auth_header)
    assert own.status_code == 200


@pytest.mark.django_db
def test_sec_p1_02_throttle_nfe_create(
    api_client, auth_header, tenant_a, provider_sp, customer_b2b, nfe_settings
):
    cache.clear()
    body = {
        "idempotency_key": "nfe-th-1",
        "provider_id": str(provider_sp.id),
        "customer_id": str(customer_b2b.id),
        "nature_operation": "VENDA",
    }
    with patch.object(NfeWriteThrottle, "THROTTLE_RATES", {"nfe_write": "1/min"}):
        first = api_client.post(
            reverse("nfe-invoices"), body, format="json", **auth_header
        )
        assert first.status_code == 201, first.data
        body["idempotency_key"] = "nfe-th-2"
        second = api_client.post(
            reverse("nfe-invoices"), body, format="json", **auth_header
        )
        assert second.status_code == 429
