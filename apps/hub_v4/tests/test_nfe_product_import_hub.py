"""Hub — importação produtos NF-e."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.nfe.product_import import TEMPLATE_FILENAME, generate_template_xlsx


@pytest.fixture
def hub_import(db, settings):
    settings.NFE_ENABLED = True
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-import-hub",
        legal_name="Import Hub",
        document="60746948000112",
        settings={"nfe_enabled": True},
    )
    user = User.objects.create_user(
        email="import.hub@exeq.local", password="Secret123!", name="Import"
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
def test_products_list_import_buttons(client, hub_import):
    tenant, user = hub_import
    _login(client, tenant, user)
    body = client.get(reverse("hub-v4-nfe-products")).content.decode()
    assert reverse("hub-v4-nfe-product-import") in body
    assert reverse("hub-v4-nfe-product-import-template") in body
    assert "Importar produtos" in body


@pytest.mark.django_db
def test_download_template(client, hub_import):
    tenant, user = hub_import
    _login(client, tenant, user)
    resp = client.get(reverse("hub-v4-nfe-product-import-template"))
    assert resp.status_code == 200
    assert TEMPLATE_FILENAME in resp["Content-Disposition"]
    assert len(resp.content) > 1000
    assert resp.content[:2] == b"PK"
