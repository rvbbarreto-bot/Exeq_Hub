"""Gestão de usuários do tenant no Hub (tenant_admin + max_users)."""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.accounts.membership_services import invite_or_link_user, update_membership
from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.plan_limits import PlanLimitError
from apps.accounts.plan_services import assign_plan, ensure_system_plans
from apps.accounts.services import ensure_system_roles


@pytest.fixture
def hub_users_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    ensure_system_plans()
    tenant = Tenant.objects.create(
        slug="users-hub-qa",
        legal_name="Users Hub QA",
        document="34028316000103",
    )
    assign_plan(tenant=tenant, plan="starter")  # max_users=2
    admin = User.objects.create_user(
        email="admin.hub@exeq.local", password="Secret123!", name="Admin Hub"
    )
    mem = TenantMembership.objects.create(
        tenant=tenant, user=admin, role=roles["tenant_admin"], is_active=True
    )
    return tenant, admin, roles, mem


def _login(client, tenant, user, password="Secret123!"):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": password,
        },
    )


@pytest.mark.django_db
def test_hub_users_list_and_invite(client, hub_users_ctx):
    tenant, admin, _roles, _mem = hub_users_ctx
    _login(client, tenant, admin)
    r = client.get(reverse("hub-v4-users"))
    assert r.status_code == 200
    assert b"Usu" in r.content
    assert b"1/2" in r.content or b"usu" in r.content.lower()

    r = client.post(
        reverse("hub-v4-user-invite"),
        {
            "email": "op@exeq.local",
            "name": "Operador",
            "password": "Secret123!",
            "role_code": "operator",
            "is_active": "1",
        },
    )
    assert r.status_code == 302
    assert TenantMembership.objects.filter(
        tenant=tenant, user__email="op@exeq.local", is_active=True
    ).exists()

    # starter max 2 users
    r = client.get(reverse("hub-v4-user-invite"))
    assert r.status_code == 302
    assert reverse("hub-v4-users") in r.url

    r = client.post(
        reverse("hub-v4-user-invite"),
        {
            "email": "third@exeq.local",
            "name": "Terceiro",
            "password": "Secret123!",
            "role_code": "readonly",
            "is_active": "1",
        },
    )
    assert r.status_code == 200  # form error
    assert not TenantMembership.objects.filter(
        tenant=tenant, user__email="third@exeq.local"
    ).exists()


@pytest.mark.django_db
def test_hub_operator_cannot_invite(client, hub_users_ctx):
    tenant, admin, roles, _mem = hub_users_ctx
    op = User.objects.create_user(
        email="only.op@exeq.local", password="Secret123!", name="Only Op"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=op, role=roles["operator"], is_active=True
    )
    _login(client, tenant, op)
    r = client.get(reverse("hub-v4-user-invite"))
    assert r.status_code == 302
    assert reverse("hub-v4-dashboard") in r.url


@pytest.mark.django_db
def test_cannot_deactivate_last_admin(hub_users_ctx):
    tenant, admin, roles, mem = hub_users_ctx
    with pytest.raises(ValueError, match="último administrador"):
        update_membership(
            membership=mem,
            is_active=False,
            actor_user=admin,
        )


@pytest.mark.django_db
def test_invite_links_existing_user(hub_users_ctx):
    tenant, admin, roles, _mem = hub_users_ctx
    existing = User.objects.create_user(
        email="shared@exeq.local", password="OldPass99!", name="Shared"
    )
    # bump plan so quota allows 2nd? starter is 2, already 1
    mem, created, user_created, plain = invite_or_link_user(
        tenant=tenant,
        email="shared@exeq.local",
        name="Shared Renamed",
        password="",
        role_code="accountant",
        is_active=True,
    )
    assert created is True
    assert user_created is False
    assert plain == ""
    assert mem.user_id == existing.id
    assert mem.role.code == "accountant"
    existing.refresh_from_db()
    assert existing.name == "Shared Renamed"


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_invite_generates_password_and_sends_email(client, hub_users_ctx, mailoutbox):
    tenant, admin, _roles, _mem = hub_users_ctx
    assign_plan(tenant=tenant, plan="contabil_5")
    _login(client, tenant, admin)
    r = client.post(
        reverse("hub-v4-user-invite"),
        {
            "email": "new.op@exeq.local",
            "name": "New Op",
            "password": "",
            "role_code": "operator",
            "is_active": "1",
            "send_invite_email": "1",
        },
    )
    assert r.status_code == 302
    assert TenantMembership.objects.filter(
        tenant=tenant, user__email="new.op@exeq.local"
    ).exists()
    assert len(mailoutbox) == 1
    assert "new.op@exeq.local" in mailoutbox[0].to
    assert "EXEQ Hub" in mailoutbox[0].subject or "Convite" in mailoutbox[0].subject
    assert tenant.slug in mailoutbox[0].body
    assert "Senha inicial:" in mailoutbox[0].body
