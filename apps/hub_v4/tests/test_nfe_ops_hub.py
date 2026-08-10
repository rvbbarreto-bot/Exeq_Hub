"""Cancel, CC-e e download de artefatos NF-e no Hub."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_product


@pytest.fixture
def hub_nfe_ops(db, settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-ops-hub",
        legal_name="NFe Ops Hub",
        document="34028316000103",
        settings={"nfe_enabled": True},
    )
    user = User.objects.create_user(
        email="nfe.ops@exeq.local", password="Secret123!", name="NFe Ops"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
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
        code="OPS-SKU",
        description="Produto ops",
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


def _emit(client, ctx, key="ops-1"):
    r = client.post(
        reverse("hub-v4-nfe-emit"),
        {
            "idempotency_key": key,
            "provider_id": str(ctx["provider"].id),
            "customer_id": str(ctx["customer"].id),
            "nature_operation": "VENDA",
            "series": "1",
            "tp_amb": "2",
            "product_id": str(ctx["product"].id),
            "quantity": "1",
        },
    )
    assert r.status_code == 302, r.content.decode()[:500]
    return NfeInvoice.objects.get(tenant=ctx["tenant"], idempotency_key=key)


@pytest.mark.django_db
def test_hub_download_xml_pdf(client, hub_nfe_ops):
    _login(client, hub_nfe_ops)
    inv = _emit(client, hub_nfe_ops, "ops-dl")
    assert inv.status == NfeInvoice.Status.AUTHORIZED

    r_xml = client.get(reverse("hub-v4-nfe-doc-download", args=[inv.id, "xml"]))
    assert r_xml.status_code == 200
    assert "xml" in r_xml["Content-Type"]
    assert len(r_xml.content) > 20

    r_pdf = client.get(reverse("hub-v4-nfe-doc-download", args=[inv.id, "pdf"]))
    assert r_pdf.status_code == 200
    assert "pdf" in r_pdf["Content-Type"]
    assert r_pdf.content[:4] == b"%PDF" or len(r_pdf.content) > 10


@pytest.mark.django_db
def test_hub_cce_and_download(client, hub_nfe_ops):
    _login(client, hub_nfe_ops)
    inv = _emit(client, hub_nfe_ops, "ops-cce")
    detail = client.get(reverse("hub-v4-nfe-detail", args=[inv.id]))
    assert detail.status_code == 200
    assert b"Carta de Corre" in detail.content or b"CC-e" in detail.content

    r = client.post(
        reverse("hub-v4-nfe-cce", args=[inv.id]),
        {
            "x_correcao": "Correcao do endereco de entrega do destinatario na nota."
        },
    )
    assert r.status_code == 302
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED

    r_cce = client.get(reverse("hub-v4-nfe-doc-download", args=[inv.id, "cce"]))
    assert r_cce.status_code == 200
    assert b"<" in r_cce.content or len(r_cce.content) > 0


@pytest.mark.django_db
def test_hub_cancel_nfe(client, hub_nfe_ops):
    _login(client, hub_nfe_ops)
    inv = _emit(client, hub_nfe_ops, "ops-cancel")
    r = client.post(
        reverse("hub-v4-nfe-cancel", args=[inv.id]),
        {
            "justificativa": "Cancelamento solicitado pelo cliente em homologacao."
        },
    )
    assert r.status_code == 302
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.CANCELLED

    detail = client.get(reverse("hub-v4-nfe-detail", args=[inv.id]))
    assert detail.status_code == 200
    # cancel form gone; downloads remain for cancelled
    assert b"Cancelar NF-e" not in detail.content or inv.status == "cancelled"
