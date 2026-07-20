import pytest

from apps.accounts.models import TenantMembership, User


@pytest.mark.django_db
def test_login_success_returns_tokens_and_role(api_client, tenant_a, user_ana, membership_admin):
    response = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": "acme",
            "email": "ana@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["role_code"] == "tenant_admin"
    assert response.data["tenant_slug"] == "acme"


@pytest.mark.django_db
def test_login_wrong_password_returns_401(api_client, tenant_a, user_ana, membership_admin):
    response = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": "acme",
            "email": "ana@exeq.local",
            "password": "wrong",
        },
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_login_without_membership_returns_401(api_client, tenant_a, tenant_b, roles):
    user = User.objects.create_user(email="solo@exeq.local", password="Secret123!", name="Solo")
    TenantMembership.objects.create(tenant=tenant_b, user=user, role=roles["operator"])
    response = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": "acme",
            "email": "solo@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_login_inactive_user_returns_401(api_client, tenant_a, user_ana, membership_admin):
    user_ana.is_active = False
    user_ana.save(update_fields=["is_active"])
    response = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": "acme",
            "email": "ana@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert response.status_code == 401
