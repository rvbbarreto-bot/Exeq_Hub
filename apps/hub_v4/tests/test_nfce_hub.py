"""Hub NFC-e — navegação e PDV."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.nfe.services import create_product


@pytest.fixture
def hub_nfce(db, settings):
    from apps.accounts.models import Tenant, TenantMembership, User
    from apps.accounts.services import ensure_system_roles
    from apps.master_data.models import Provider, TaxRegime

    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfce-hub",
        legal_name="NFCe Hub",
        document="37229907000137",
        settings={"nfse_enabled": True, "nfe_enabled": True, "nfce_enabled": True},
    )
    user = User.objects.create_user(
        email="nfce.hub@exeq.local", password="Secret123!", name="NFCe Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=roles["tenant_admin"],
        is_active=True,
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="PDV Lab",
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
    product = create_product(
        tenant=tenant,
        code="HUB1",
        description="Item hub",
        ncm="21069090",
        unit_price_cents=1500,
        csosn="102",
    )
    return {"tenant": tenant, "user": user, "provider": provider, "product": product}


def _login(client, hub_nfce):
    r = client.post(
        reverse("hub-v4-login"),
        {
            "email": hub_nfce["user"].email,
            "password": "Secret123!",
            "tenant_slug": hub_nfce["tenant"].slug,
        },
    )
    assert r.status_code == 302


@pytest.mark.django_db
def test_hub_nfce_nav_and_pdv_emit(client, hub_nfce):
    _login(client, hub_nfce)
    dash = client.get(reverse("hub-v4-dashboard"))
    body = dash.content.decode()
    assert reverse("hub-v4-nfce-list") in body
    assert "NFC-e Avulsa" in body

    pdv = client.get(reverse("hub-v4-nfce-pdv"))
    assert pdv.status_code == 200
    assert b"NFC-e Avulsa" in pdv.content

    emit = client.post(
        reverse("hub-v4-nfce-pdv"),
        {
            "idempotency_key": "hub-pdv-1",
            "provider_id": str(hub_nfce["provider"].id),
            "line_product_id": [str(hub_nfce["product"].id)],
            "line_quantity": ["2"],
            "payment_method": "99",
        },
    )
    assert emit.status_code == 302
    from apps.nfce.models import NfceInvoice

    inv = NfceInvoice.objects.get(tenant=hub_nfce["tenant"], idempotency_key="hub-pdv-1")
    assert inv.status == NfceInvoice.Status.AUTHORIZED
    assert inv.payment_method == "99"

    detail = client.get(reverse("hub-v4-nfce-detail", args=[inv.id]))
    assert detail.status_code == 200
    xml = client.get(reverse("hub-v4-nfce-doc-download", args=[inv.id, "xml"]))
    assert xml.status_code == 200
    assert b"<mod>65</mod>" in xml.content

    pdf = client.get(reverse("hub-v4-nfce-doc-download", args=[inv.id, "pdf"]))
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_hub_nfce_avulsa_multi_item(client, hub_nfce):
    product2 = create_product(
        tenant=hub_nfce["tenant"],
        code="HUB2",
        description="Segundo item",
        ncm="21069090",
        unit_price_cents=2000,
        csosn="102",
    )
    _login(client, hub_nfce)
    emit = client.post(
        reverse("hub-v4-nfce-pdv"),
        {
            "idempotency_key": "hub-avulsa-multi",
            "provider_id": str(hub_nfce["provider"].id),
            "line_product_id": [
                str(hub_nfce["product"].id),
                str(product2.id),
            ],
            "line_quantity": ["2", "1"],
            "payment_method": "17",
        },
    )
    assert emit.status_code == 302
    from apps.nfce.models import NfceInvoice

    inv = NfceInvoice.objects.prefetch_related("items").get(
        tenant=hub_nfce["tenant"], idempotency_key="hub-avulsa-multi"
    )
    assert inv.status == NfceInvoice.Status.AUTHORIZED
    assert inv.payment_method == "17"
    assert inv.items.count() == 2
    assert inv.total_cents == 1500 * 2 + 2000


@pytest.mark.django_db
def test_hub_nfce_cnpj_redirects_nfe_emit(client, hub_nfce):
    _login(client, hub_nfce)
    resp = client.post(
        reverse("hub-v4-nfce-pdv"),
        {
            "idempotency_key": "hub-cnpj-nfe",
            "provider_id": str(hub_nfce["provider"].id),
            "line_product_id": [str(hub_nfce["product"].id)],
            "line_quantity": ["1"],
            "payment_method": "01",
            "cnpj": "37229907000137",
        },
    )
    assert resp.status_code == 302
    assert reverse("hub-v4-nfe-emit") in resp["Location"]
    from apps.nfce.models import NfceInvoice

    assert not NfceInvoice.objects.filter(
        tenant=hub_nfce["tenant"], idempotency_key="hub-cnpj-nfe"
    ).exists()


@pytest.mark.django_db
def test_hub_nfce_hidden_without_flag(client, hub_nfce, settings):
    hub_nfce["tenant"].settings = {"nfse_enabled": True, "nfce_enabled": False}
    hub_nfce["tenant"].save(update_fields=["settings"])
    _login(client, hub_nfce)
    dash = client.get(reverse("hub-v4-dashboard"))
    assert reverse("hub-v4-nfce-list") not in dash.content.decode()
