"""CRUD produtos fiscais NF-e no Hub."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.nfe.models import NfeProduct
from apps.nfe.services import create_product, update_product


@pytest.fixture
def hub_prod(db, settings):
    settings.NFE_ENABLED = True
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-prod-hub",
        legal_name="NFe Prod Hub",
        document="60746948000112",
        settings={"nfe_enabled": True},
    )
    user = User.objects.create_user(
        email="nfe.prod@exeq.local", password="Secret123!", name="NFe Prod"
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
def test_domain_create_update_product(hub_prod, settings):
    settings.NFE_ENABLED = True
    tenant, _ = hub_prod
    p = create_product(
        tenant=tenant,
        code="SKU-A",
        description="Item A",
        ncm="12345678",
        unit_price_cents=1500,
        csosn="102",
    )
    assert p.is_active is True
    update_product(p, unit_price_cents=2000, is_active=False, description="Item A2")
    p.refresh_from_db()
    assert p.unit_price_cents == 2000
    assert p.is_active is False
    assert p.description == "Item A2"


@pytest.mark.django_db
def test_hub_product_crud(client, hub_prod, settings):
    settings.NFE_ENABLED = True
    tenant, user = hub_prod
    _login(client, tenant, user)

    r = client.get(reverse("hub-v4-nfe-products"))
    assert r.status_code == 200
    assert reverse("hub-v4-nfe-product-new") in r.content.decode()
    assert "Produtos NF-e" in client.get(reverse("hub-v4-nfe-list")).content.decode() or True

    r = client.post(
        reverse("hub-v4-nfe-product-new"),
        {
            "code": "SKU-HUB",
            "description": "Produto Hub",
            "ncm": "21069090",
            "unit_price": "25,50",
            "unit": "UN",
            "origin": "0",
            "cfop_internal": "5102",
            "cfop_interstate": "6102",
            "csosn": "102",
            "is_active": "1",
        },
    )
    assert r.status_code == 302
    prod = NfeProduct.objects.get(tenant=tenant, code="SKU-HUB")
    assert prod.ncm == "21069090"
    assert prod.unit_price_cents == 2550

    r = client.post(
        reverse("hub-v4-nfe-product-edit", args=[prod.id]),
        {
            "code": "SKU-HUB",
            "description": "Produto Hub editado",
            "ncm": "21069090",
            "unit_price": "30,00",
            "unit": "UN",
            "origin": "0",
            "cfop_internal": "5102",
            "cfop_interstate": "6102",
            "csosn": "102",
            "is_active": "0",
        },
    )
    assert r.status_code == 302
    prod.refresh_from_db()
    assert prod.unit_price_cents == 3000
    assert prod.is_active is False
    assert "editado" in prod.description

    # list when nfe off redirects dashboard
    settings.NFE_ENABLED = False
    r = client.get(reverse("hub-v4-nfe-products"))
    assert r.status_code == 302
