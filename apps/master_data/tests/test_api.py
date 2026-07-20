import pytest
from django.db import IntegrityError

from apps.master_data.services import create_customer, create_provider
from shared.validators import validate_cnpj, validate_cpf


@pytest.mark.django_db
def test_invalid_cnpj_rejected():
    with pytest.raises(ValueError):
        validate_cnpj("12345678000100")


@pytest.mark.django_db
def test_create_provider_and_customer_api(api_client, auth_header, tenant_a):
    provider = api_client.post(
        "/api/v1/providers/",
        {
            "document": "00000000000191",
            "legal_name": "Prestador ACME",
            "tax_regime": "simples_nacional",
        },
        format="json",
        **auth_header,
    )
    assert provider.status_code == 201
    assert provider.data["document"] == "00000000000191"

    customer = api_client.post(
        "/api/v1/customers/",
        {
            "document": "52998224725",
            "document_type": "cpf",
            "name": "Cliente",
        },
        format="json",
        **auth_header,
    )
    assert customer.status_code == 201

    service = api_client.post(
        "/api/v1/services/",
        {"service_code": "1.01", "description": "Serviço teste"},
        format="json",
        **auth_header,
    )
    assert service.status_code == 201

    listing = api_client.get("/api/v1/providers/", **auth_header)
    assert listing.status_code == 200
    assert len(listing.data) >= 1


@pytest.mark.django_db
def test_tenant_isolation_on_providers(api_client, auth_header, tenant_a, tenant_b, roles):
    create_provider(
        tenant=tenant_b,
        document="00000000000272",
        legal_name="Outro",
        tax_regime="simples_nacional",
    )
    create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Meu",
        tax_regime="simples_nacional",
    )
    response = api_client.get("/api/v1/providers/", **auth_header)
    assert response.status_code == 200
    docs = {item["document"] for item in response.data}
    assert docs == {"00000000000191"}


@pytest.mark.django_db
def test_same_document_allowed_across_tenants(tenant_a, tenant_b):
    create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="A",
    )
    create_customer(
        tenant=tenant_b,
        document="52998224725",
        document_type="cpf",
        name="B",
    )


@pytest.mark.django_db
def test_same_document_blocked_inside_tenant(tenant_a):
    create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="A",
    )
    with pytest.raises(IntegrityError):
        create_customer(
            tenant=tenant_a,
            document="52998224725",
            document_type="cpf",
            name="Dup",
        )


@pytest.mark.django_db
def test_readonly_cannot_create_provider(api_client, tenant_a, roles):
    from apps.accounts.models import TenantMembership, User

    user = User.objects.create_user(email="ro@exeq.local", password="Secret123!", name="RO")
    TenantMembership.objects.create(tenant=tenant_a, user=user, role=roles["readonly"])
    login = api_client.post(
        "/api/v1/auth/login",
        {"tenant_slug": "acme", "email": "ro@exeq.local", "password": "Secret123!"},
        format="json",
    )
    header = {"HTTP_AUTHORIZATION": f"Bearer {login.data['access']}"}
    response = api_client.post(
        "/api/v1/providers/",
        {
            "document": "00000000000191",
            "legal_name": "X",
            "tax_regime": "simples_nacional",
        },
        format="json",
        **header,
    )
    assert response.status_code == 403
