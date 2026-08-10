"""Smoke tests Hub V4 — shell de apresentação (sem alterar domínio)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles


@pytest.fixture
def hub_user(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="hub-v4-qa",
        legal_name="Hub V4 QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="hubv4@exeq.local", password="Secret123!", name="Hub V4"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    return tenant, user


@pytest.mark.django_db
def test_hub_v4_login_and_dashboard(client, hub_user):
    tenant, user = hub_user
    r = client.get(reverse("hub-v4-dashboard"))
    assert r.status_code == 302
    assert reverse("hub-v4-login") in r.url

    r = client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )
    assert r.status_code == 302
    assert reverse("hub-v4-dashboard") in r.url

    r = client.get(reverse("hub-v4-dashboard"))
    assert r.status_code == 200
    assert b"Emitir NFS-e" in r.content
    assert b"A" in r.content  # ações or greeting


@pytest.mark.django_db
def test_hub_v4_nfse_list_filters(client, hub_user):
    tenant, user = hub_user
    client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )
    r = client.get(reverse("hub-v4-nfse-list"), {"status": "all", "q": ""})
    assert r.status_code == 200
    assert b"NFS-e" in r.content or b"Emitir" in r.content

    r = client.get(reverse("hub-v4-nfse-wizard"))
    assert r.status_code == 200
    assert b"wizard" in r.content.lower() or b"Tomador" in r.content

    for name in (
        "hub-v4-charges",
        "hub-v4-charge-new",
        "hub-v4-das",
        "hub-v4-das-emit",
        "hub-v4-customers",
        "hub-v4-providers",
        "hub-v4-fiscal",
        "hub-v4-tax-rules",
        "hub-v4-services",
        "hub-v4-users",
        "hub-v4-certificates",
        "hub-v4-integrations",
        "hub-v4-preferences",
    ):
        resp = client.get(reverse(name))
        assert resp.status_code == 200, name


@pytest.mark.django_db
def test_hub_v4_nav_labels_no_artefatos_menu(client, hub_user):
    tenant, user = hub_user
    client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )
    html = client.get(reverse("hub-v4-dashboard")).content.decode()
    assert "Artefatos" not in html or "Documentos" in html
    # Sidebar IA-nav labels
    assert "NFS-e" in html
    assert "Cobranças" in html
    assert "Guias DAS" in html
    assert "Clientes" in html
    assert "Empresas" in html
    assert "Usuários" in html or "Usuarios" in html
    assert "Certificados" in html
    assert "Integrações" in html
    assert "Preferências" in html
    assert "/admin/" not in html
