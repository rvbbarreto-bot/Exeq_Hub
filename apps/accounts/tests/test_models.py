import pytest
from django.db import IntegrityError

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles


@pytest.mark.django_db
def test_tenant_slug_and_document_are_unique():
    Tenant.objects.create(
        slug="acme",
        legal_name="ACME LTDA",
        document="12345678000199",
    )
    with pytest.raises(IntegrityError):
        Tenant.objects.create(
            slug="acme",
            legal_name="Other",
            document="99888777000166",
        )


@pytest.mark.django_db
def test_user_email_is_globally_unique_and_password_is_hashed():
    user = User.objects.create_user(
        email="a@exeq.local",
        password="secret-pass-1",
        name="Ana",
    )
    assert user.password != "secret-pass-1"
    assert user.check_password("secret-pass-1")
    with pytest.raises(IntegrityError):
        User.objects.create_user(
            email="a@exeq.local",
            password="other",
            name="Outro",
        )


@pytest.mark.django_db
def test_membership_unique_per_tenant_user():
    tenant = Tenant.objects.create(
        slug="beta",
        legal_name="Beta",
        document="11222333000144",
    )
    user = User.objects.create_user(email="b@exeq.local", password="x", name="B")
    roles = ensure_system_roles()
    admin = next(r for r in roles if r.code == "tenant_admin")
    TenantMembership.objects.create(tenant=tenant, user=user, role=admin)
    with pytest.raises(IntegrityError):
        TenantMembership.objects.create(tenant=tenant, user=user, role=admin)


@pytest.mark.django_db
def test_ensure_system_roles_is_idempotent():
    first = ensure_system_roles()
    second = ensure_system_roles()
    assert len(first) == 4
    assert {r.code for r in first} == {r.code for r in second}
