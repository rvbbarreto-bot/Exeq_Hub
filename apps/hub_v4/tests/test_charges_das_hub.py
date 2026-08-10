"""Emissão de cobrança e DAS no Hub V4."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID
from django.urls import reverse

from apps.accounts.certificates import upload_a1_certificate
from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.billing.models import Charge
from apps.das.models import GuiaFiscal
from apps.master_data.models import Customer, Provider, TaxRegime


def _make_pfx(password: bytes = b"secret", days: int = 90) -> bytes:
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


@pytest.fixture
def hub_bill(db, tmp_path, settings):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.STORAGE_BACKEND = "local"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="bill-hub-qa",
        legal_name="Bill Hub QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="bill.hub@exeq.local", password="Secret123!", name="Bill Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    customer = Customer.objects.create(
        tenant=tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente Cob",
        is_active=True,
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="Prest DAS",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
    )
    upload_a1_certificate(
        tenant=tenant,
        label="A1 lab",
        cnpj=provider.document,
        pfx_bytes=_make_pfx(),
        password="secret",
        provider=provider,
    )
    return {
        "tenant": tenant,
        "user": user,
        "customer": customer,
        "provider": provider,
    }


def _login(client, ctx):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_create_charge_simple(client, hub_bill, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    _login(client, hub_bill)
    due = (date.today() + timedelta(days=5)).isoformat()
    r = client.post(
        reverse("hub-v4-charge-new"),
        {
            "idempotency_key": "hub-bill-1",
            "customer_id": str(hub_bill["customer"].id),
            "amount": "10,00",
            "due_date": due,
            "description": "Honorários",
            "charge_kind": "simple",
        },
    )
    assert r.status_code == 302
    charge = Charge.objects.get(tenant=hub_bill["tenant"], idempotency_key="hub-bill-1")
    assert charge.amount_cents == 1000
    assert reverse("hub-v4-charge-detail", args=[charge.id]) in r.url
    detail = client.get(reverse("hub-v4-charge-detail", args=[charge.id]))
    assert detail.status_code == 200
    assert b"Linha digit" in detail.content or b"gateway" in detail.content.lower()


@pytest.mark.django_db
def test_hub_emit_das_stub(client, hub_bill, settings):
    settings.RECEITA_HTTP_MODE = "stub"
    _login(client, hub_bill)
    r = client.post(
        reverse("hub-v4-das-emit"),
        {
            "idempotency_key": "hub-das-1",
            "provider_id": str(hub_bill["provider"].id),
            "tipo_guia": "DAS",
            "competencia": "2026-06",
            "versao_atual": "1",
        },
    )
    assert r.status_code == 302, r.content.decode()[:500]
    guia = GuiaFiscal.objects.get(tenant=hub_bill["tenant"], idempotency_key="hub-das-1")
    assert guia.tipo_guia == "DAS"
    assert guia.competencia == "2026-06"
    detail = client.get(reverse("hub-v4-das-detail", args=[guia.id]))
    assert detail.status_code == 200
    assert b"2026-06" in detail.content
