import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def roles(db):
    return {r.code: r for r in ensure_system_roles()}


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(
        slug="acme",
        legal_name="ACME LTDA",
        document="00000000000191",
    )


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(
        slug="beta",
        legal_name="Beta LTDA",
        document="00000000000272",
    )


@pytest.fixture
def user_ana(db):
    return User.objects.create_user(email="ana@exeq.local", password="Secret123!", name="Ana")


@pytest.fixture
def membership_admin(tenant_a, user_ana, roles):
    return TenantMembership.objects.create(
        tenant=tenant_a,
        user=user_ana,
        role=roles["tenant_admin"],
    )


@pytest.fixture
def auth_header(api_client, tenant_a, user_ana, membership_admin):
    response = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": tenant_a.slug,
            "email": user_ana.email,
            "password": "Secret123!",
        },
        format="json",
    )
    assert response.status_code == 200
    return {"HTTP_AUTHORIZATION": f"Bearer {response.data['access']}"}


@pytest.fixture(autouse=True)
def _celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.NF_SYNC_PROCESSING = True
    settings.FOCUS_HTTP_MODE = "stub"
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.EVOLUTION_HTTP_MODE = "stub"
