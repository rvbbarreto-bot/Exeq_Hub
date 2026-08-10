"""Hub multi-CNPJ: Empresas, tomadores, header e sem CTAs Admin."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Provider, TaxRegime


@pytest.fixture
def hub_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="multi-cnpj-qa",
        legal_name="Escritório Multi CNPJ",
        document="11222333000181",
        settings={"max_emit_cnpjs": 2},
    )
    user = User.objects.create_user(
        email="multi@exeq.local", password="Secret123!", name="Contador QA"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    return tenant, user


def _login(client, tenant, user):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_no_admin_cta_for_clients(client, hub_ctx):
    tenant, user = hub_ctx
    _login(client, tenant, user)
    for name in (
        "hub-v4-dashboard",
        "hub-v4-customers",
        "hub-v4-providers",
        "hub-v4-integrations",
        "hub-v4-preferences",
        "hub-v4-login",
    ):
        html = client.get(reverse(name)).content.decode()
        assert "/admin/" not in html, name
        assert "Ir ao Admin" not in html


@pytest.mark.django_db
def test_hub_providers_list_and_create(client, hub_ctx):
    tenant, user = hub_ctx
    _login(client, tenant, user)

    r = client.get(reverse("hub-v4-providers"))
    assert r.status_code == 200
    assert b"Empresas" in r.content
    assert b"0/2" in r.content

    r = client.post(
        reverse("hub-v4-provider-new"),
        {
            "document": "04.252.011/0001-10",
            "legal_name": "Cliente Alpha Ltda",
            "trade_name": "Alpha",
            "tax_regime": TaxRegime.SIMPLES,
            "municipal_registration": "123",
            "is_active": "1",
            "data_source": "manual",
            "uf": "SP",
            "municipio": "Atibaia",
        },
    )
    assert r.status_code == 302
    assert Provider.objects.filter(tenant=tenant, document="04252011000110").exists()

    # second
    r = client.post(
        reverse("hub-v4-provider-new"),
        {
            "document": "00000000000191",
            "legal_name": "Cliente Beta Ltda",
            "tax_regime": TaxRegime.SIMPLES,
            "is_active": "1",
            "data_source": "manual",
        },
    )
    assert r.status_code == 302
    assert Provider.objects.filter(tenant=tenant).count() == 2

    # third blocked by plan (POST re-renders form with error)
    r = client.post(
        reverse("hub-v4-provider-new"),
        {
            "document": "11444777000161",
            "legal_name": "Cliente Gama",
            "tax_regime": TaxRegime.SIMPLES,
            "is_active": "1",
            "data_source": "manual",
        },
    )
    assert r.status_code == 200
    assert b"Limite" in r.content or b"limite" in r.content
    assert Provider.objects.filter(tenant=tenant, document="11444777000161").exists() is False

    r = client.get(reverse("hub-v4-provider-new"))
    assert r.status_code == 302
    assert reverse("hub-v4-providers") in r.url


@pytest.mark.django_db
def test_active_company_header_and_wizard(client, hub_ctx):
    tenant, user = hub_ctx
    _login(client, tenant, user)
    p = Provider.objects.create(
        tenant=tenant,
        document="04252011000110",
        legal_name="Empresa Header SA",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
    )
    r = client.post(
        reverse("hub-v4-set-active-company"),
        {"provider_id": str(p.id), "next": reverse("hub-v4-dashboard")},
    )
    assert r.status_code == 302
    html = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert "Empresa ativa" in html
    assert "Empresa Header SA" in html or "04252011000110" in html
    assert "Empresas" in html  # nav

    wh = client.get(reverse("hub-v4-nfse-wizard")).content.decode()
    assert "Emitir como" in wh
    assert str(p.id) in wh


@pytest.mark.django_db
def test_hub_customer_create(client, hub_ctx):
    tenant, user = hub_ctx
    _login(client, tenant, user)
    r = client.post(
        reverse("hub-v4-customer-new"),
        {
            "document_type": "cnpj",
            "document": "04.252.011/0001-10",
            "name": "Tomador QA",
            "email": "tomador@example.com",
            "is_active": "1",
            "data_source": "manual",
            "uf": "SP",
        },
    )
    assert r.status_code == 302
    from apps.master_data.models import Customer

    assert Customer.objects.filter(tenant=tenant, name="Tomador QA").exists()
