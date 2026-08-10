"""Emissão NF-e (modelo 55) no Hub V4."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_product


@pytest.fixture
def hub_nfe_emit(db, settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-emit-hub",
        legal_name="NFe Emit Hub",
        document="11222333000181",
        settings={"nfe_enabled": True},
    )
    user = User.objects.create_user(
        email="nfe.emit@exeq.local", password="Secret123!", name="NFe Emit"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={
            "logradouro": "Rua Jose Florido",
            "numero": "121",
            "bairro": "Jardim",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )
    customer = Customer.objects.create(
        tenant=tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente B2B",
        is_active=True,
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
    product = create_product(
        tenant=tenant,
        code="SKU-HUB",
        description="Produto Hub",
        ncm="12345678",
        unit_price_cents=10000,
        csosn="102",
    )
    return {
        "tenant": tenant,
        "user": user,
        "provider": provider,
        "customer": customer,
        "product": product,
    }


def _login(client, ctx):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_emit_nfe_with_product(client, hub_nfe_emit):
    _login(client, hub_nfe_emit)
    r = client.get(reverse("hub-v4-nfe-emit"))
    assert r.status_code == 200
    assert b"Emitir NF-e" in r.content or b"item" in r.content.lower()

    r = client.post(
        reverse("hub-v4-nfe-emit"),
        {
            "idempotency_key": "hub-nfe-1",
            "provider_id": str(hub_nfe_emit["provider"].id),
            "customer_id": str(hub_nfe_emit["customer"].id),
            "nature_operation": "VENDA",
            "series": "1",
            "tp_amb": "2",
            "ind_ie_dest": "9",
            "issue_date": "2026-08-01",
            "product_id": str(hub_nfe_emit["product"].id),
            "quantity": "2",
        },
    )
    assert r.status_code == 302, r.content.decode()[:800]
    inv = NfeInvoice.objects.get(
        tenant=hub_nfe_emit["tenant"], idempotency_key="hub-nfe-1"
    )
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert inv.total_cents == 20000
    assert reverse("hub-v4-nfe-detail", args=[inv.id]) in r.url

    detail = client.get(reverse("hub-v4-nfe-detail", args=[inv.id]))
    assert detail.status_code == 200
    assert inv.access_key.encode() in detail.content or b"chave" in detail.content.lower()


@pytest.mark.django_db
def test_hub_emit_nfe_manual_item(client, hub_nfe_emit):
    _login(client, hub_nfe_emit)
    r = client.post(
        reverse("hub-v4-nfe-emit"),
        {
            "idempotency_key": "hub-nfe-manual",
            "provider_id": str(hub_nfe_emit["provider"].id),
            "customer_id": str(hub_nfe_emit["customer"].id),
            "nature_operation": "VENDA",
            "series": "1",
            "tp_amb": "2",
            "product_id": "",
            "item_code": "MAN-1",
            "item_description": "Item manual",
            "item_ncm": "12345678",
            "unit_price": "50,00",
            "quantity": "1",
            "csosn": "102",
        },
    )
    assert r.status_code == 302
    inv = NfeInvoice.objects.get(
        tenant=hub_nfe_emit["tenant"], idempotency_key="hub-nfe-manual"
    )
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert inv.total_cents == 5000


@pytest.mark.django_db
def test_hub_nfe_list_has_emit_cta(client, hub_nfe_emit):
    _login(client, hub_nfe_emit)
    r = client.get(reverse("hub-v4-nfe-list"))
    assert r.status_code == 200
    assert reverse("hub-v4-nfe-emit") in r.content.decode()
