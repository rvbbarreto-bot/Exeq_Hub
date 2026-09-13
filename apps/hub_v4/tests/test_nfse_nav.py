"""Hub: navegação NFS-e condicionada a nfse_enabled."""

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, TenantRole, User
from apps.accounts.services import ensure_system_roles


@pytest.fixture
def hub_nfse_nav(db, settings):
    settings.NFE_ENABLED = False
    ensure_system_roles()
    tenant = Tenant.objects.create(
        slug="nfse-only",
        legal_name="NFSe Only",
        document="00000000000196",
        settings={"nfse_enabled": True, "nfe_enabled": False},
    )
    role = TenantRole.objects.get(code="tenant_admin")
    user = User.objects.create_user(
        email="nfse.only@exeq.local", password="Secret123!", name="NFSe"
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role=role, is_active=True)
    return tenant, user


def _login(client, tenant_user):
    tenant, user = tenant_user
    client.post(
        reverse("hub-v4-login"),
        {"tenant_slug": tenant.slug, "email": user.email, "password": "Secret123!"},
    )


@pytest.mark.django_db
def test_nfse_nav_inside_exeq_fiscal(client, hub_nfse_nav):
    _login(client, hub_nfse_nav)
    body = client.get(reverse("hub-v4-dashboard")).content.decode()
    fiscal_idx = body.index("Exeq Fiscal")
    nfse_idx = body.index("Emissão NFS-e")
    assert fiscal_idx < nfse_idx
    assert "nav-accordion" in body[fiscal_idx:nfse_idx + 80]
    assert reverse("hub-v4-nfse-list") in body


@pytest.mark.django_db
def test_nfse_nav_when_enabled(client, hub_nfse_nav):
    _login(client, hub_nfse_nav)
    r = client.get(reverse("hub-v4-dashboard"))
    assert r.status_code == 200
    body = r.content.decode()
    assert reverse("hub-v4-nfse-list") in body or "/hub/nfse/" in body
    assert "NF-e" not in body or "nfe" not in body.lower()


@pytest.mark.django_db
def test_nfse_list_blocked_when_disabled(client, hub_nfse_nav):
    tenant, user = hub_nfse_nav
    tenant.settings = {"nfse_enabled": False, "nfe_enabled": False}
    tenant.save(update_fields=["settings", "updated_at"])
    _login(client, (tenant, user))
    r = client.get(reverse("hub-v4-nfse-list"))
    assert r.status_code == 302
    assert reverse("hub-v4-dashboard") in r.url


@pytest.mark.django_db
def test_nfse_only_tenant_still_has_providers(client, hub_nfse_nav):
    _login(client, hub_nfse_nav)
    r = client.get(reverse("hub-v4-providers"))
    assert r.status_code == 200
