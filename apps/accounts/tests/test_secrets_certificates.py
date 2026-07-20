from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID

from apps.accounts.certificates import (
    assert_certificate_usable,
    scan_expiring_certificates,
    upload_a1_certificate,
)
from apps.accounts.exceptions import CertificateNotUsableError
from apps.accounts.models import DigitalCertificate
from apps.accounts.secrets import get_tenant_secret_plaintext, set_tenant_secret
from apps.ops.models import OutboxMessage
from apps.issuance.models import NfIssue
from apps.issuance.polling import poll_nf_issue_status
from integrations.evolution.client import EvolutionHttpGateway
from integrations.nfse.focus import FocusNfseProvider


def _make_pfx(password: bytes = b"secret", days: int = 60) -> bytes:
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
        encryption_algorithm=BestAvailableEncryption(password),
    )


@pytest.mark.django_db
def test_tenant_secret_roundtrip(tenant_a):
    set_tenant_secret(
        tenant=tenant_a,
        provider="focus",
        key_name="api_token",
        plaintext="token-secreto",
    )
    assert (
        get_tenant_secret_plaintext(
            tenant=tenant_a,
            provider="focus",
            key_name="api_token",
        )
        == "token-secreto"
    )


@pytest.mark.django_db
def test_upload_a1_parses_validity(tenant_a, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    pfx = _make_pfx(days=60)
    cert = upload_a1_certificate(
        tenant=tenant_a,
        label="A1 Test",
        cnpj="00000000000191",
        pfx_bytes=pfx,
        password="secret",
    )
    assert cert.status == DigitalCertificate.Status.ACTIVE
    assert cert.is_primary is True
    assert cert.key_usage == ["das", "nfse"]
    assert cert.not_after > datetime.now(timezone.utc)
    assert cert.stored_file.purpose == "certificate"
    assert cert.password_secret_id is not None
    assert (
        get_tenant_secret_plaintext(
            tenant=tenant_a,
            provider="certificate",
            key_name=f"pfx_password:{cert.id}",
        )
        == "secret"
    )


@pytest.mark.django_db
def test_assert_certificate_blocks_missing_and_expired(tenant_a, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    with pytest.raises(CertificateNotUsableError):
        assert_certificate_usable(tenant=tenant_a, cnpj="00000000000191", purpose="das")

    expired = upload_a1_certificate(
        tenant=tenant_a,
        label="Expired",
        cnpj="00000000000191",
        pfx_bytes=_make_pfx(days=0),
        password="secret",
    )
    # force expired status for gate
    DigitalCertificate.objects.filter(id=expired.id).update(
        status=DigitalCertificate.Status.EXPIRED,
        not_after=datetime.now(timezone.utc) - timedelta(days=1),
    )
    with pytest.raises(CertificateNotUsableError):
        assert_certificate_usable(tenant=tenant_a, cnpj="00000000000191", purpose="das")


@pytest.mark.django_db
def test_rotation_demotes_previous_primary(tenant_a, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    first = upload_a1_certificate(
        tenant=tenant_a,
        label="v1",
        cnpj="00000000000191",
        pfx_bytes=_make_pfx(days=90),
        password="secret",
    )
    second = upload_a1_certificate(
        tenant=tenant_a,
        label="v2",
        cnpj="00000000000191",
        pfx_bytes=_make_pfx(days=120),
        password="secret",
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.is_primary is False
    assert second.is_primary is True
    assert second.version == first.version + 1


@pytest.mark.django_db
def test_scan_expiring_enqueues_outbox(tenant_a, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    upload_a1_certificate(
        tenant=tenant_a,
        label="Soon",
        cnpj="00000000000191",
        pfx_bytes=_make_pfx(days=10),
        password="secret",
    )
    n = scan_expiring_certificates(alert_days=30)
    assert n >= 1
    assert OutboxMessage.objects.filter(event_type="certificate.expiring").exists()


@pytest.mark.django_db
def test_poll_authorizes_when_provider_ready(tenant_a, monkeypatch):
    from datetime import date

    from apps.fiscal.models import FiscalProfile
    from apps.master_data.models import TaxRegime
    from apps.master_data.services import create_customer, create_provider, create_service

    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="P",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="C",
    )
    service = create_service(tenant=tenant_a, service_code="1.01", description="S")
    profile = FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN",
        tax_regime=TaxRegime.SIMPLES,
    )
    issue = NfIssue.objects.create(
        tenant=tenant_a,
        idempotency_key="poll-1",
        status=NfIssue.Status.POLLING,
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=profile,
        ibge_code="3504107",
        competence_date=date(2024, 6, 1),
        amount_cents=1000,
        focus_ref="FOCUS-REF",
    )

    class FakeProvider:
        kind = "focus"

        def consultar(self, *, ref: str):
            from integrations.nfse.port import NfseEmitResult

            return NfseEmitResult(
                external_ref=ref,
                status="authorized",
                raw={"status": "autorizado"},
            )

    monkeypatch.setattr(
        "apps.issuance.polling.get_nfse_provider",
        lambda **kwargs: FakeProvider(),
    )
    poll_nf_issue_status(issue)
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED


def test_focus_http_emit_uses_basic_auth(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ref": "abc", "status": "autorizado"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, auth=None, headers=None, **kwargs):
            calls["method"] = method
            calls["url"] = url
            calls["auth"] = auth
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    provider = FocusNfseProvider(
        token="meu-token",
        base_url="https://homologacao.focusnfe.com.br",
        mode="http",
    )
    result = provider.emitir(
        payload={"issue_id": "11111111-1111-1111-1111-111111111111", "amount_cents": 100}
    )
    assert result.status == "authorized"
    assert calls["auth"] == ("meu-token", "")
    assert "/v2/nfse" in calls["url"]


def test_evolution_http_send(monkeypatch, settings):
    settings.EVOLUTION_API_BASE_URL = "https://evo.example"
    settings.EVOLUTION_API_KEY = "key"
    settings.EVOLUTION_INSTANCE = "exeq"

    class FakeResponse:
        status_code = 201

        def json(self):
            return {"key": {"id": "msg-1"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert "sendText/exeq" in url
            assert headers["apikey"] == "key"
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gateway = EvolutionHttpGateway()
    result = gateway.send_text(phone_e164="+5511999999999", text="oi")
    assert result["ok"] is True
    assert result["ref"] == "msg-1"
