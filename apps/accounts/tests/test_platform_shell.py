"""Redirects de legado + superusuário de plataforma."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from apps.accounts.models import TenantMembership


@pytest.mark.django_db
def test_legacy_app_and_cadastros_redirect_to_hub(client):
    for url in ("/app/", "/app/index.html", "/cadastros/", "/cadastros/customers/novo/"):
        r = client.get(url)
        assert r.status_code == 302
        assert r.url == "/hub/"


@pytest.mark.django_db
def test_ensure_platform_admin_wipe_only_exeq_admin(tenant_a, user_ana, membership_admin):
    assert TenantMembership.objects.filter(user=user_ana).exists()
    call_command(
        "ensure_platform_admin",
        "--wipe-others",
        "--email",
        "exeq_admin@exeq.local",
        "--password",
        "ExeqAdmin#2026!",
    )
    User = get_user_model()
    assert User.objects.count() == 1
    admin = User.objects.get()
    assert admin.email == "exeq_admin@exeq.local"
    assert admin.is_superuser and admin.is_staff and admin.is_platform_admin
    assert admin.check_password("ExeqAdmin#2026!")
    assert not TenantMembership.objects.filter(user=admin).exists()


@pytest.mark.django_db
def test_admin_login_page_available(client):
    r = client.get("/admin/login/")
    assert r.status_code == 200
    # Admin clássico (sem shell Unfold)
    body = r.content.decode().lower()
    assert "django" in body or "username" in body or "e-mail" in body or "email" in body


@pytest.mark.django_db
def test_hub_login_still_available(client):
    r = client.get(reverse("hub-v4-login"))
    assert r.status_code == 200
    assert b"tenant" in r.content.lower() or b"Tenant" in r.content
