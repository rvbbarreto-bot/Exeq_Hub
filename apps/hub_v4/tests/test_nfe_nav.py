"""NF-e no Hub: opt-in por tenant + flag global."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles


@pytest.fixture
def hub_nfe_tenant(db, settings):
    settings.NFE_ENABLED = True
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-qa",
        legal_name="NFe QA",
        document="11222333000181",
        settings={"nfe_enabled": True},
    )
    user = User.objects.create_user(
        email="nfeqa@exeq.local", password="Secret123!", name="NFe QA"
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
def test_nfe_nav_and_list_when_enabled(client, hub_nfe_tenant, settings):
    settings.NFE_ENABLED = True
    tenant, user = hub_nfe_tenant
    assert _login(client, tenant, user).status_code == 302
    dash = client.get(reverse("hub-v4-dashboard"))
    assert dash.status_code == 200
    body = dash.content.decode()
    assert "NF-e" in body
    assert reverse("hub-v4-nfe-list") in body or "/hub/nfe/" in body

    r = client.get(reverse("hub-v4-nfe-list"))
    assert r.status_code == 200
    assert b"NF-e" in r.content


@pytest.mark.django_db
def test_nfe_hidden_without_tenant_flag(client, hub_nfe_tenant, settings):
    settings.NFE_ENABLED = True
    tenant, user = hub_nfe_tenant
    tenant.settings = {}
    tenant.save(update_fields=["settings"])
    _login(client, tenant, user)
    body = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert 'href="/hub/nfe/"' not in body and reverse("hub-v4-nfe-list") not in body
    r = client.get(reverse("hub-v4-nfe-list"))
    assert r.status_code == 302
    assert reverse("hub-v4-dashboard") in r.url


@pytest.mark.django_db
def test_nfe_hidden_when_global_off(client, hub_nfe_tenant, settings):
    settings.NFE_ENABLED = False
    tenant, user = hub_nfe_tenant
    _login(client, tenant, user)
    body = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert reverse("hub-v4-nfe-list") not in body
    assert 'href="/hub/nfe/"' not in body
