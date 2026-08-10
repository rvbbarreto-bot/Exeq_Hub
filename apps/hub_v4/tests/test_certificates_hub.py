"""Upload de certificado A1 no Hub, vinculado a empresa/CNPJ."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import DigitalCertificate, Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Provider, TaxRegime


def _make_pfx(password: bytes = b"secret", days: int = 60) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EXEQ Hub A1")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(password),
    )


@pytest.fixture
def hub_cert_ctx(db, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="cert-hub-qa",
        legal_name="Cert Hub QA",
        document="11222333000181",
        settings={"max_emit_cnpjs": 5},
    )
    user = User.objects.create_user(
        email="cert.hub@exeq.local", password="Secret123!", name="Cert Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="04252011000110",
        legal_name="Empresa Cert SA",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
    )
    return tenant, user, provider


def _login(client, tenant, user):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_certificate_page_has_upload_no_admin(client, hub_cert_ctx):
    tenant, user, provider = hub_cert_ctx
    _login(client, tenant, user)
    r = client.get(reverse("hub-v4-certificates"))
    assert r.status_code == 200
    html = r.content.decode()
    assert "Enviar certificado A1" in html
    assert str(provider.id) in html
    assert "/admin/" not in html
    assert "Empresa Cert SA" in html


@pytest.mark.django_db
def test_hub_upload_a1_links_provider(client, hub_cert_ctx):
    tenant, user, provider = hub_cert_ctx
    _login(client, tenant, user)
    pfx = _make_pfx()
    upload = SimpleUploadedFile(
        "empresa.pfx", pfx, content_type="application/x-pkcs12"
    )
    r = client.post(
        reverse("hub-v4-certificates"),
        {
            "provider_id": str(provider.id),
            "label": "A1 Homolog",
            "password": "secret",
            "make_primary": "1",
            "file": upload,
        },
    )
    assert r.status_code == 302
    assert reverse("hub-v4-certificates") in r.url
    cert = DigitalCertificate.objects.get(tenant=tenant, cnpj=provider.document)
    assert cert.label == "A1 Homolog"
    assert cert.is_primary is True
    assert cert.provider_id == provider.id
    assert cert.status == DigitalCertificate.Status.ACTIVE


@pytest.mark.django_db
def test_hub_upload_a1_bad_password(client, hub_cert_ctx):
    tenant, user, provider = hub_cert_ctx
    _login(client, tenant, user)
    pfx = _make_pfx(password=b"right")
    upload = SimpleUploadedFile("bad.pfx", pfx, content_type="application/x-pkcs12")
    r = client.post(
        reverse("hub-v4-certificates"),
        {
            "provider_id": str(provider.id),
            "label": "A1",
            "password": "wrong",
            "file": upload,
        },
    )
    assert r.status_code == 200
    assert DigitalCertificate.objects.filter(tenant=tenant).count() == 0
