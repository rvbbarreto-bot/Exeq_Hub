import pytest

from apps.accounts.auth_services import authenticate_for_tenant, issue_tokens
from apps.accounts.models import Tenant, TenantMembership, User
from shared.exceptions import AuthenticationError


# --- unitários (domínio) ---


@pytest.mark.django_db
def test_authenticate_for_tenant_success(tenant_a, user_ana, membership_admin):
    user, membership = authenticate_for_tenant(
        tenant_slug="acme",
        email="ana@exeq.local",
        password="Secret123!",
    )
    assert user.pk == user_ana.pk
    assert membership.pk == membership_admin.pk
    assert membership.role.code == "tenant_admin"
    user_ana.refresh_from_db()
    assert user_ana.last_login_at is not None


@pytest.mark.django_db
def test_authenticate_for_tenant_wrong_password(tenant_a, user_ana, membership_admin):
    with pytest.raises(AuthenticationError, match="Credenciais inválidas"):
        authenticate_for_tenant(
            tenant_slug="acme",
            email="ana@exeq.local",
            password="wrong",
        )


@pytest.mark.django_db
def test_authenticate_for_tenant_suspended(tenant_a, user_ana, membership_admin):
    tenant_a.status = Tenant.Status.SUSPENDED
    tenant_a.save(update_fields=["status"])
    with pytest.raises(AuthenticationError, match="Tenant indisponível"):
        authenticate_for_tenant(
            tenant_slug="acme",
            email="ana@exeq.local",
            password="Secret123!",
        )


@pytest.mark.django_db
def test_issue_tokens_embeds_tenant_claims(tenant_a, user_ana, membership_admin):
    payload = issue_tokens(user_ana, membership_admin)
    assert payload["tenant_slug"] == "acme"
    assert payload["tenant_legal_name"] == tenant_a.legal_name
    assert payload["role_code"] == "tenant_admin"
    assert payload["user_name"] == user_ana.name
    assert payload["user_email"] == user_ana.email
    assert payload["access"]
    assert payload["refresh"]


# --- integrados (endpoints HTTP) ---


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
    assert response.data["tenant_legal_name"] == tenant_a.legal_name
    assert response.data["user_name"] == "Ana"
    assert response.data["user_email"] == "ana@exeq.local"


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


@pytest.mark.django_db
def test_login_invalid_payload_returns_400(api_client):
    response = api_client.post(
        "/api/v1/auth/login",
        {"tenant_slug": "acme", "email": "not-an-email"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_refresh_returns_new_access(api_client, tenant_a, user_ana, membership_admin):
    login = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": "acme",
            "email": "ana@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert login.status_code == 200
    refreshed = api_client.post(
        "/api/v1/auth/refresh",
        {"refresh": login.data["refresh"]},
        format="json",
    )
    assert refreshed.status_code == 200
    assert "access" in refreshed.data


@pytest.mark.django_db
def test_login_token_authorizes_protected_endpoint(
    api_client, tenant_a, user_ana, membership_admin
):
    login = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": "acme",
            "email": "ana@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert login.status_code == 200
    denied = api_client.get("/api/v1/certificates/")
    assert denied.status_code in (401, 403)
    allowed = api_client.get(
        "/api/v1/certificates/",
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
    )
    assert allowed.status_code == 200
