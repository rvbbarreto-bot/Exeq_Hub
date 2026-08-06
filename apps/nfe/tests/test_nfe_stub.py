"""NF-e greenfield — draft → validate → emit stub → cancel."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice, NfeProduct
from apps.nfe.services import (
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
    validate_invoice,
)


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",  # ok em stub
        address={
            "logradouro": "Rua Jose Florido",
            "numero": "121",
            "bairro": "Jardim Alvinopolis",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente B2B",
        address={
            "logradouro": "Av Teste",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_emit_stub_flow(nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="SKU1",
        description="Produto lab",
        ncm="12345678",
        unit_price_cents=10000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="nfe-lab-1",
    )
    replace_items(
        inv,
        items=[
            {
                "product_id": str(product.id),
                "quantity": "2",
            }
        ],
    )
    inv.refresh_from_db()
    result = validate_invoice(inv)
    assert result["ok"] is True
    assert result["totals"]["total_cents"] == 20000

    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert inv.number == 1
    assert inv.number_consumed is True
    assert len(inv.access_key) == 44
    assert inv.fiscal_snapshot is not None
    assert inv.fiscal_snapshot["emitente"]["cnpj"] == "37229907000137"
    from apps.nfe.services import allowed_actions

    assert "cancel" in allowed_actions(inv)
    assert "emit" not in allowed_actions(inv)


@pytest.mark.django_db
def test_disabled_blocks(tenant_a, provider_sp, customer_b2b, settings):
    settings.NFE_ENABLED = False
    with pytest.raises(Exception) as exc:
        create_draft(
            tenant=tenant_a,
            provider=provider_sp,
            customer=customer_b2b,
            idempotency_key="x",
        )
    assert "desabilitada" in str(exc.value).lower() or exc.value.code == "nfe_disabled"


@pytest.mark.django_db
def test_api_emit_flow(api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_b2b):
    r = api_client.get("/api/v1/nfe/gate/", **auth_header)
    assert r.status_code == 200
    assert r.data["enabled"] is True
    assert r.data["can_create"] is True

    prod = api_client.post(
        "/api/v1/nfe/products/",
        {
            "code": "P1",
            "description": "Item API",
            "ncm": "21069090",
            "unit_price_cents": 5000,
            "csosn": "102",
            "unit": "UN",
            "origin": "0",
            "cfop_internal": "5102",
        },
        format="json",
        **auth_header,
    )
    assert prod.status_code == 201, prod.data

    draft = api_client.post(
        "/api/v1/nfe/invoices/",
        {
            "idempotency_key": "api-nfe-1",
            "provider_id": str(provider_sp.id),
            "customer_id": str(customer_b2b.id),
        },
        format="json",
        **auth_header,
    )
    assert draft.status_code == 201, draft.data
    inv_id = draft.data["id"]
    version = draft.data["version"]

    items = api_client.put(
        f"/api/v1/nfe/invoices/{inv_id}/items",
        {
            "version": version,
            "items": [{"product_id": prod.data["id"], "quantity": "1"}],
        },
        format="json",
        **auth_header,
    )
    assert items.status_code == 200, items.data
    version = items.data["version"]

    val = api_client.post(
        f"/api/v1/nfe/invoices/{inv_id}/validate",
        {},
        format="json",
        **auth_header,
    )
    assert val.status_code == 200
    assert val.data["validation"]["ok"] is True
    version = val.data["invoice"]["version"]

    emit = api_client.post(
        f"/api/v1/nfe/invoices/{inv_id}/emit",
        {"version": version},
        format="json",
        **auth_header,
    )
    assert emit.status_code == 202, emit.data
    assert emit.data["status"] == "authorized"
    assert "cancel" in emit.data["allowed_actions"]

    cancel = api_client.post(
        f"/api/v1/nfe/invoices/{inv_id}/cancel",
        {"justificativa": "Cancelamento de teste em homologacao stub"},
        format="json",
        **auth_header,
    )
    assert cancel.status_code == 200, cancel.data
    assert cancel.data["status"] == "cancelled"


@pytest.mark.django_db
def test_number_series_increments(nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a, code="A", description="A", ncm="11111111", unit_price_cents=100
    )
    for i in range(2):
        inv = create_draft(
            tenant=tenant_a,
            provider=provider_sp,
            customer=customer_b2b,
            idempotency_key=f"nfe-num-{i}",
        )
        replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
        emit_invoice(inv)
        inv.refresh_from_db()
        assert inv.number == i + 1
