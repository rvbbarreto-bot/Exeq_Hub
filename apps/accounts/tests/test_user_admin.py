"""Admin User — criação com senha e reset."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.admin import UserAdmin
from apps.accounts.admin_user_forms import UserAddForm, UserResetPasswordForm
from apps.accounts.models import User


def _staff_request(*, method="get", path="/", data=None):
    UserModel = get_user_model()
    staff = UserModel.objects.create_superuser(
        email="staff-user-admin@exeq.local",
        password="Secret123!",
        name="Staff",
    )
    factory = RequestFactory()
    if method == "post":
        request = factory.post(path, data or {})
    else:
        request = factory.get(path)
    request.user = staff
    setattr(request, "session", "session")
    setattr(request, "_messages", FallbackStorage(request))
    return request


@pytest.mark.django_db
def test_user_add_form_hashes_password():
    form = UserAddForm(
        data={
            "email": "novo@exeq.local",
            "name": "Novo",
            "password1": "Secret123!",
            "password2": "Secret123!",
            "is_active": True,
            "is_staff": False,
            "is_platform_admin": False,
        }
    )
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.check_password("Secret123!")


@pytest.mark.django_db
def test_user_add_form_rejects_mismatch():
    form = UserAddForm(
        data={
            "email": "novo@exeq.local",
            "name": "Novo",
            "password1": "Secret123!",
            "password2": "Outra123!",
            "is_active": True,
        }
    )
    assert not form.is_valid()
    assert "password2" in form.errors


@pytest.mark.django_db
def test_user_admin_save_model_on_add_hashes_password():
    site = AdminSite()
    model_admin = UserAdmin(User, site)
    request = _staff_request()
    form = UserAddForm(
        data={
            "email": "criado-admin@exeq.local",
            "name": "Criado Admin",
            "password1": "MinhaSenh8",
            "password2": "MinhaSenh8",
            "is_active": True,
        }
    )
    assert form.is_valid(), form.errors
    model_admin.save_model(request, form.instance, form, change=False)
    user = User.objects.get(email="criado-admin@exeq.local")
    assert user.check_password("MinhaSenh8")


@pytest.mark.django_db
def test_user_admin_reset_password_get_renders():
    user = User.objects.create_user(
        email="reset-get@exeq.local",
        password="Antiga123!",
        name="Reset Get",
    )
    from django.test import Client

    staff = User.objects.create_superuser(
        email="staff-reset-get@exeq.local",
        password="Secret123!",
        name="Staff Reset",
    )
    client = Client()
    client.force_login(staff)
    path = reverse("admin:accounts_user_reset_password", args=[user.pk])
    response = client.get(path)
    assert response.status_code == 200
    assert b"Redefinir senha" in response.content
    assert user.email.encode() in response.content


@pytest.mark.django_db
def test_user_admin_reset_password_view():
    user = User.objects.create_user(
        email="reset-me@exeq.local",
        password="Antiga123!",
        name="Reset Me",
    )
    site = AdminSite()
    model_admin = UserAdmin(User, site)
    path = reverse("admin:accounts_user_reset_password", args=[user.pk])
    request = _staff_request(
        method="post",
        path=path,
        data={"password1": "NovaSenh8!", "password2": "NovaSenh8!"},
    )
    response = model_admin.reset_password_view(request, str(user.pk))
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("NovaSenh8!")
    assert not user.check_password("Antiga123!")


@pytest.mark.django_db
def test_user_reset_password_form_rejects_short_password():
    form = UserResetPasswordForm(
        data={"password1": "curta", "password2": "curta"},
    )
    assert not form.is_valid()
