from decimal import Decimal

import pytest

from apps.accounts.certificates import upload_a1_certificate
from apps.accounts.exceptions import CertificateNotUsableError
from apps.ops.models import StoredFile
from apps.das.exceptions import DuplicateDasNaturalKeyError
from apps.das.models import GuiaFiscal
from apps.das.services import emitir_guia
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider
from shared.storage import get_storage


def _pfx(days=60):
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption,
        pkcs12,
    )
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EXEQ Test")])
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
        encryption_algorithm=BestAvailableEncryption(b"secret"),
    )


@pytest.fixture
def provider(tenant_a):
    return create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador DAS",
        tax_regime=TaxRegime.SIMPLES,
    )


@pytest.fixture
def cert_a1(tenant_a, provider, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    return upload_a1_certificate(
        tenant=tenant_a,
        label="A1 DAS",
        cnpj=provider.document,
        pfx_bytes=_pfx(),
        password="secret",
        provider=provider,
        key_usage=["das", "nfse"],
    )


@pytest.mark.django_db
def test_emitir_das_requires_certificate(tenant_a, provider):
    with pytest.raises(CertificateNotUsableError):
        emitir_guia(
            tenant=tenant_a,
            idempotency_key="das-no-cert",
            provider=provider,
            tipo_guia=GuiaFiscal.TipoGuia.DAS,
            competencia="2024-06",
        )


@pytest.mark.django_db
def test_emitir_das_idempotent_and_total(tenant_a, provider, cert_a1):
    first = emitir_guia(
        tenant=tenant_a,
        idempotency_key="das-1",
        provider=provider,
        tipo_guia=GuiaFiscal.TipoGuia.DAS,
        competencia="2024-06",
    )
    second = emitir_guia(
        tenant=tenant_a,
        idempotency_key="das-1",
        provider=provider,
        tipo_guia=GuiaFiscal.TipoGuia.DAS,
        competencia="2024-06",
    )
    assert first.id == second.id
    first.refresh_from_db()
    assert first.status == GuiaFiscal.Status.DISPONIVEL
    assert first.compliance_status == GuiaFiscal.ComplianceStatus.APROVADO
    assert first.valor_total == first.valor_principal + first.valor_multa + first.valor_juros
    assert first.valor_total == Decimal("150.75")
    assert first.pdf_file_id is not None
    assert first.pdf_file.purpose == "das_pdf"
    assert first.pdf_storage_key == first.pdf_file.object_key
    assert get_storage().get(key=first.pdf_file.object_key).startswith(b"%PDF")
    assert StoredFile.objects.filter(tenant=tenant_a, purpose="das_pdf").count() == 1


@pytest.mark.django_db
def test_duplicate_natural_key_blocked(tenant_a, provider, cert_a1):
    emitir_guia(
        tenant=tenant_a,
        idempotency_key="das-2",
        provider=provider,
        tipo_guia=GuiaFiscal.TipoGuia.DAS,
        competencia="2024-07",
        versao_atual=1,
    )
    with pytest.raises(DuplicateDasNaturalKeyError):
        emitir_guia(
            tenant=tenant_a,
            idempotency_key="das-3",
            provider=provider,
            tipo_guia=GuiaFiscal.TipoGuia.DAS,
            competencia="2024-07",
            versao_atual=1,
        )


@pytest.mark.django_db
def test_das_api(api_client, auth_header, tenant_a, provider, cert_a1):
    response = api_client.post(
        "/api/v1/das/guias/",
        {
            "idempotency_key": "api-das-1",
            "provider_id": str(provider.id),
            "tipo_guia": "DAS",
            "competencia": "2024-08",
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 201
    assert response.data["status"] == "DISPONIVEL"
    assert str(response.data["valor_total"]) == "150.75"
