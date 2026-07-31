from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from cryptography.x509.oid import NameOID
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import TenantMembership, User
from apps.accounts.secrets import get_tenant_secret_plaintext
from apps.billing.exceptions import InvalidProviderCredentialsError
from apps.billing.models import PaymentProviderAudit
from apps.billing.provider_services import (
    get_inter_credentials_metadata,
    mask_secret,
    save_inter_credentials,
)
from integrations.payments.errors import PaymentGatewayError


def _pem_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "EXEQ Inter Test")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(Encoding.PEM).decode()
    key_pem = key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    return cert_pem, key_pem


@pytest.fixture
def membership_readonly(tenant_a, roles):
    user = User.objects.create_user(
        email="ro@exeq.local", password="Secret123!", name="RO"
    )
    return TenantMembership.objects.create(
        tenant=tenant_a,
        user=user,
        role=roles["readonly"],
    )


@pytest.fixture
def auth_readonly(api_client, tenant_a, membership_readonly):
    response = api_client.post(
        "/api/v1/auth/login",
        {
            "tenant_slug": tenant_a.slug,
            "email": "ro@exeq.local",
            "password": "Secret123!",
        },
        format="json",
    )
    assert response.status_code == 200
    return {"HTTP_AUTHORIZATION": f"Bearer {response.data['access']}"}


def test_mask_secret():
    assert mask_secret("e3c6f480-secret") == "e3c6****"
    assert mask_secret("") == ""


@pytest.mark.django_db
def test_save_inter_credentials_valid(tenant_a, user_ana):
    cert_pem, key_pem = _pem_pair()
    meta = save_inter_credentials(
        tenant=tenant_a,
        client_id="e3c6f480-aaaa",
        client_secret="super-secret-value",
        cert_pem=cert_pem,
        key_pem=key_pem,
        conta_corrente="123456",
        actor_user=user_ana,
    )
    assert meta["configured"] is True
    assert meta["client_id_masked"] == "e3c6****"
    assert "super-secret" not in str(meta)
    assert get_tenant_secret_plaintext(
        tenant=tenant_a, provider="inter", key_name="client_secret"
    ) == "super-secret-value"
    assert PaymentProviderAudit.objects.filter(
        tenant=tenant_a, action="credentials_updated"
    ).exists()


@pytest.mark.django_db
def test_save_inter_credentials_invalid_pem(tenant_a):
    with pytest.raises(InvalidProviderCredentialsError):
        save_inter_credentials(
            tenant=tenant_a,
            client_id="id",
            client_secret="sec",
            cert_pem="not-a-cert",
            key_pem="not-a-key",
        )
    assert not PaymentProviderAudit.objects.filter(tenant=tenant_a).exists()
    assert (
        get_tenant_secret_plaintext(
            tenant=tenant_a, provider="inter", key_name="client_id"
        )
        is None
    )


@pytest.mark.django_db
def test_get_inter_metadata_never_leaks_secrets(tenant_a):
    cert_pem, key_pem = _pem_pair()
    save_inter_credentials(
        tenant=tenant_a,
        client_id="abcd1234",
        client_secret="leak-me-secret",
        cert_pem=cert_pem,
        key_pem=key_pem,
    )
    meta = get_inter_credentials_metadata(tenant=tenant_a)
    blob = str(meta)
    assert "leak-me-secret" not in blob
    assert "BEGIN CERTIFICATE" not in blob
    assert "BEGIN PRIVATE" not in blob
    assert meta["has_client_secret"] is True
    assert meta["has_cert"] is True


@pytest.mark.django_db
def test_api_put_provider(api_client, auth_header, tenant_a):
    response = api_client.put(
        "/api/v1/billing/provider",
        {"provider": "inter"},
        format="json",
        **auth_header,
    )
    assert response.status_code == 200
    assert response.data["provider"] == "inter"
    tenant_a.refresh_from_db()
    assert tenant_a.settings.get("payment_provider") == "inter"


@pytest.mark.django_db
def test_api_put_provider_invalid(api_client, auth_header):
    response = api_client.put(
        "/api/v1/billing/provider",
        {"provider": "foobank"},
        format="json",
        **auth_header,
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_inter_credentials_multipart(api_client, auth_header, tenant_a):
    cert_pem, key_pem = _pem_pair()
    response = api_client.post(
        "/api/v1/billing/providers/inter/credentials",
        {
            "client_id": "cid-1111",
            "client_secret": "secret-should-not-leak",
            "conta_corrente": "999",
            "cert_file": SimpleUploadedFile("c.crt", cert_pem.encode()),
            "key_file": SimpleUploadedFile("k.key", key_pem.encode()),
        },
        format="multipart",
        **auth_header,
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "secret-should-not-leak" not in body
    assert "BEGIN CERTIFICATE" not in body
    assert response.data["configured"] is True
    assert response.data["client_id_masked"].startswith("cid-")


@pytest.mark.django_db
def test_api_inter_credentials_invalid_pem_no_persist(api_client, auth_header, tenant_a):
    response = api_client.post(
        "/api/v1/billing/providers/inter/credentials",
        {
            "client_id": "cid",
            "client_secret": "sec",
            "cert_file": SimpleUploadedFile("c.crt", b"bad"),
            "key_file": SimpleUploadedFile("k.key", b"bad"),
        },
        format="multipart",
        **auth_header,
    )
    assert response.status_code == 400
    assert get_tenant_secret_plaintext(
        tenant=tenant_a, provider="inter", key_name="client_id"
    ) is None


@pytest.mark.django_db
def test_api_get_inter_credentials_masked(api_client, auth_header, tenant_a):
    cert_pem, key_pem = _pem_pair()
    save_inter_credentials(
        tenant=tenant_a,
        client_id="zzzz9999",
        client_secret="hidden-secret",
        cert_pem=cert_pem,
        key_pem=key_pem,
    )
    response = api_client.get(
        "/api/v1/billing/providers/inter/credentials",
        **auth_header,
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "hidden-secret" not in body
    assert "BEGIN PRIVATE" not in body
    assert response.data["client_id_masked"] == "zzzz****"


@pytest.mark.django_db
def test_api_asaas_credentials(api_client, auth_header, tenant_a):
    response = api_client.post(
        "/api/v1/billing/providers/asaas/credentials",
        {"api_token": "asaas-token-secret"},
        format="json",
        **auth_header,
    )
    assert response.status_code == 200
    assert "asaas-token-secret" not in response.content.decode()
    assert response.data["configured"] is True
    assert get_tenant_secret_plaintext(
        tenant=tenant_a, provider="asaas", key_name="api_token"
    ) == "asaas-token-secret"


@pytest.mark.django_db
def test_api_test_connection_ok(api_client, auth_header, tenant_a, monkeypatch):
    cert_pem, key_pem = _pem_pair()
    save_inter_credentials(
        tenant=tenant_a,
        client_id="id",
        client_secret="sec",
        cert_pem=cert_pem,
        key_pem=key_pem,
    )

    class FakeAuth:
        def get_access_token(self, *, force=False):
            return "tok"

        def close(self):
            return None

    monkeypatch.setattr(
        "apps.billing.provider_services.build_inter_auth_client",
        lambda **kwargs: FakeAuth(),
    )
    response = api_client.post(
        "/api/v1/billing/providers/inter/test-connection",
        **auth_header,
    )
    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert "tok" not in response.content.decode()


@pytest.mark.django_db
def test_api_test_connection_error(api_client, auth_header, tenant_a, monkeypatch):
    cert_pem, key_pem = _pem_pair()
    save_inter_credentials(
        tenant=tenant_a,
        client_id="id",
        client_secret="sec",
        cert_pem=cert_pem,
        key_pem=key_pem,
    )

    class FakeAuth:
        def get_access_token(self, *, force=False):
            raise PaymentGatewayError("OAuth Inter HTTP 401")

        def close(self):
            return None

    monkeypatch.setattr(
        "apps.billing.provider_services.build_inter_auth_client",
        lambda **kwargs: FakeAuth(),
    )
    response = api_client.post(
        "/api/v1/billing/providers/inter/test-connection",
        **auth_header,
    )
    assert response.status_code == 502
    assert response.data["status"] == "error"


@pytest.mark.django_db
def test_api_writer_required_for_put(api_client, auth_readonly):
    response = api_client.put(
        "/api/v1/billing/provider",
        {"provider": "c6"},
        format="json",
        **auth_readonly,
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_api_readonly_can_get_provider(api_client, auth_readonly):
    response = api_client.get("/api/v1/billing/provider", **auth_readonly)
    assert response.status_code == 200
    assert "provider" in response.data
