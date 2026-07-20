from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.accounts.exceptions import ElectronicProxyNotUsableError
from apps.accounts.models import ElectronicProxy
from apps.accounts.proxies import (
    assert_electronic_proxy_usable,
    das_requires_electronic_proxy,
    get_usable_proxy,
    refresh_proxy_status,
)
from apps.accounts.proxy_views import ElectronicProxyCreateSerializer, ElectronicProxyListCreateView
from apps.das.models import GuiaFiscal
from apps.das.services import emitir_guia
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider


@pytest.mark.django_db
def test_das_requires_proxy_only_in_http_mode(settings):
    settings.RECEITA_HTTP_MODE = "stub"
    settings.DAS_REQUIRE_ELECTRONIC_PROXY = False
    assert das_requires_electronic_proxy() is False
    settings.RECEITA_HTTP_MODE = "http"
    assert das_requires_electronic_proxy() is True
    settings.RECEITA_HTTP_MODE = "stub"
    settings.DAS_REQUIRE_ELECTRONIC_PROXY = True
    assert das_requires_electronic_proxy() is True


@pytest.mark.django_db
def test_assert_proxy_usable(tenant_a):
    today = timezone.localdate()
    ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        proxy_document="12345678000199",
        proxy_document_type=ElectronicProxy.DocumentType.CNPJ,
        ecac_service_codes=["PGDASD", "GERARDAS12"],
        status=ElectronicProxy.Status.ACTIVE,
        valid_from=today - timedelta(days=10),
        valid_to=today + timedelta(days=100),
        label="Procuração QA",
    )
    proxy = assert_electronic_proxy_usable(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        service_code="PGDASD",
    )
    assert proxy.label == "Procuração QA"


@pytest.mark.django_db
def test_refresh_proxy_status_branches(tenant_a):
    today = timezone.localdate()
    revoked = ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        proxy_document="1",
        status=ElectronicProxy.Status.REVOKED,
        valid_from=today - timedelta(days=10),
        valid_to=today + timedelta(days=10),
    )
    assert refresh_proxy_status(revoked).status == ElectronicProxy.Status.REVOKED

    expired = ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000272",
        proxy_document="2",
        status=ElectronicProxy.Status.ACTIVE,
        valid_from=today - timedelta(days=100),
        valid_to=today - timedelta(days=1),
    )
    assert refresh_proxy_status(expired).status == ElectronicProxy.Status.EXPIRED

    expiring = ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000353",
        proxy_document="3",
        status=ElectronicProxy.Status.ACTIVE,
        valid_from=today - timedelta(days=10),
        valid_to=today + timedelta(days=15),
    )
    assert refresh_proxy_status(expiring).status == ElectronicProxy.Status.EXPIRING

    pending = ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000434",
        proxy_document="4",
        status=ElectronicProxy.Status.PENDING,
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=100),
    )
    assert refresh_proxy_status(pending).status == ElectronicProxy.Status.ACTIVE


@pytest.mark.django_db
def test_get_usable_proxy_skips_wrong_service_and_expired(tenant_a):
    today = timezone.localdate()
    ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        proxy_document="1",
        ecac_service_codes=["OUTRO"],
        status=ElectronicProxy.Status.ACTIVE,
        valid_from=today - timedelta(days=5),
        valid_to=today + timedelta(days=100),
    )
    assert (
        get_usable_proxy(
            tenant=tenant_a,
            principal_cnpj="00.000.000/0001-91",
            service_code="PGDASD",
        )
        is None
    )
    with pytest.raises(ElectronicProxyNotUsableError):
        assert_electronic_proxy_usable(
            tenant=tenant_a,
            principal_cnpj="00000000000191",
            service_code="PGDASD",
        )


@pytest.mark.django_db
def test_get_usable_proxy_empty_codes_accepts_any(tenant_a):
    today = timezone.localdate()
    ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        proxy_document="1",
        ecac_service_codes=[],
        status=ElectronicProxy.Status.EXPIRING,
        valid_from=today - timedelta(days=5),
        valid_to=today + timedelta(days=20),
    )
    proxy = get_usable_proxy(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        service_code="QUALQUER",
    )
    assert proxy is not None


@pytest.mark.django_db
def test_emitir_guia_http_requires_proxy(tenant_a, settings, tmp_path):
    from apps.accounts.certificates import upload_a1_certificate
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption,
        pkcs12,
    )
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timezone as dt_tz

    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.RECEITA_HTTP_MODE = "http"
    settings.DAS_REQUIRE_ELECTRONIC_PROXY = False
    settings.SERPRO_CONSUMER_KEY = ""
    settings.SERPRO_CONSUMER_SECRET = ""

    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador Proxy",
        tax_regime=TaxRegime.SIMPLES,
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EXEQ")])
    now = datetime.now(dt_tz.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=60))
        .sign(key, hashes.SHA256())
    )
    pfx = pkcs12.serialize_key_and_certificates(
        name=b"t",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(b"secret"),
    )
    upload_a1_certificate(
        tenant=tenant_a,
        label="A1",
        cnpj=provider.document,
        pfx_bytes=pfx,
        password="secret",
        provider=provider,
        key_usage=["das"],
    )

    with pytest.raises(ElectronicProxyNotUsableError):
        emitir_guia(
            tenant=tenant_a,
            idempotency_key="das-no-proxy",
            provider=provider,
            tipo_guia=GuiaFiscal.TipoGuia.DAS,
            competencia="2024-06",
        )


def _proxy_request(user, tenant, *, method="GET", data=None, role_code="tenant_admin"):
    from rest_framework.test import APIRequestFactory, force_authenticate

    factory = APIRequestFactory()
    if method == "POST":
        request = factory.post("/api/v1/electronic-proxies/", data or {}, format="json")
    else:
        request = factory.get("/api/v1/electronic-proxies/")
    force_authenticate(request, user=user)
    request.tenant = tenant
    request.role_code = role_code
    return request


@pytest.mark.django_db
def test_electronic_proxy_api(tenant_a, user_ana, membership_admin):
    from django.db import connection

    connection.ensure_connection()
    today = date.today().isoformat()
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000272",
        legal_name="Prov Proxy API",
        tax_regime=TaxRegime.SIMPLES,
    )
    view = ElectronicProxyListCreateView.as_view()
    post = view(
        _proxy_request(
            user_ana,
            tenant_a,
            method="POST",
            data={
                "principal_cnpj": "00000000000191",
                "proxy_document": "12345678000199",
                "proxy_document_type": "cnpj",
                "ecac_service_codes": ["PGDASD"],
                "status": "active",
                "valid_from": today,
                "label": "API Proxy",
                "provider_id": str(provider.id),
            },
        )
    )
    assert post.status_code == 201, post.data
    assert post.data["principal_cnpj"] == "00000000000191"
    assert post.data["provider"] == provider.id
    listed = view(_proxy_request(user_ana, tenant_a))
    assert listed.status_code == 200
    assert len(listed.data) >= 1


@pytest.mark.django_db
def test_electronic_proxy_api_invalid_provider(tenant_a, user_ana, membership_admin):
    from django.db import connection

    connection.ensure_connection()
    view = ElectronicProxyListCreateView.as_view()
    response = view(
        _proxy_request(
            user_ana,
            tenant_a,
            method="POST",
            data={
                "principal_cnpj": "00000000000191",
                "proxy_document": "12345678000199",
                "valid_from": date.today().isoformat(),
                "provider_id": "00000000-0000-0000-0000-000000000099",
            },
        )
    )
    assert response.status_code == 400
    assert "provider_id" in response.data["detail"]


@pytest.mark.django_db
def test_electronic_proxy_api_invalid_cnpj(tenant_a, user_ana, membership_admin):
    from django.db import connection

    connection.ensure_connection()
    view = ElectronicProxyListCreateView.as_view()
    response = view(
        _proxy_request(
            user_ana,
            tenant_a,
            method="POST",
            data={
                "principal_cnpj": "11111111111111",
                "proxy_document": "123",
                "valid_from": date.today().isoformat(),
            },
        )
    )
    assert response.status_code == 400


def test_proxy_view_permissions_methods():
    view = ElectronicProxyListCreateView()
    view.request = MagicMock(method="POST")
    assert len(view.get_permissions()) == 1
    view.request = MagicMock(method="GET")
    assert len(view.get_permissions()) == 1


@pytest.mark.django_db
def test_create_serializer_defaults_codes(tenant_a):
    from django.db import connection

    connection.ensure_connection()
    request = MagicMock()
    request.tenant = tenant_a
    ser = ElectronicProxyCreateSerializer(
        data={
            "principal_cnpj": "00000000000191",
            "proxy_document": "12345678000199",
            "valid_from": date.today().isoformat(),
        },
        context={"request": request},
    )
    assert ser.is_valid(), ser.errors
    proxy = ser.save()
    assert "PGDASD" in proxy.ecac_service_codes
    assert "GERARDAS12" in proxy.ecac_service_codes


@pytest.mark.django_db
def test_get_usable_skips_after_refresh_marks_unusable(tenant_a, monkeypatch):
    today = timezone.localdate()
    ElectronicProxy.objects.create(
        tenant=tenant_a,
        principal_cnpj="00000000000191",
        proxy_document="1",
        ecac_service_codes=["PGDASD"],
        status=ElectronicProxy.Status.ACTIVE,
        valid_from=today - timedelta(days=5),
        valid_to=today + timedelta(days=100),
    )

    def _revoke(proxy):
        proxy.status = ElectronicProxy.Status.REVOKED
        proxy.save(update_fields=["status", "updated_at"])
        return proxy

    monkeypatch.setattr("apps.accounts.proxies.refresh_proxy_status", _revoke)
    assert get_usable_proxy(tenant=tenant_a, principal_cnpj="00000000000191") is None
