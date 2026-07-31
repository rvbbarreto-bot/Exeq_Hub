"""Testes G-SEC-P0/P1 — isolamento, XXE, throttle, retry SEFIN."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.core.cache import cache

from apps.accounts.models import TenantMembership, User
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from integrations.nfse.sefin_client import SefinHttpClient, SefinHttpError
from integrations.nfse.xml_safe import UnsafeXmlError, safe_fromstring


@pytest.fixture
def emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Serviço",
        codigo_tributacao_nacional_iss="010101",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN",
        tax_regime=TaxRegime.SIMPLES,
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)
    return {
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_ex_sec_01_tenant_cannot_read_other_nf_issue(
    api_client, auth_header, tenant_a, tenant_b, emission_setup, roles
):
    """SEC-P0-08 / EX-SEC-01: tenant A não lê NfIssue de B."""
    issue_a = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="sec-a-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=2500,
    )
    user_b = User.objects.create_user(email="bob@exeq.local", password="Secret123!", name="Bob")
    TenantMembership.objects.create(tenant=tenant_b, user=user_b, role=roles["tenant_admin"])
    login_b = api_client.post(
        "/api/v1/auth/login",
        {"tenant_slug": tenant_b.slug, "email": user_b.email, "password": "Secret123!"},
        format="json",
    )
    assert login_b.status_code == 200
    header_b = {"HTTP_AUTHORIZATION": f"Bearer {login_b.data['access']}"}

    detail = api_client.get(f"/api/v1/nf-issue/{issue_a.id}/", **header_b)
    assert detail.status_code == 404

    listing = api_client.get("/api/v1/nf-issue/", **header_b)
    assert listing.status_code == 200
    ids = {row["id"] for row in listing.data.get("results", listing.data)}
    assert str(issue_a.id) not in ids

    own = api_client.get(f"/api/v1/nf-issue/{issue_a.id}/", **auth_header)
    assert own.status_code == 200


def test_sec_p1_03_xxe_external_entity_rejected(tmp_path):
    evil = tmp_path / "secret.txt"
    evil.write_text("LEAK", encoding="utf-8")
    payload = (
        f'<?xml version="1.0"?>'
        f'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "{evil.as_uri()}">]>'
        f"<DPS><infDPS>&xxe;</infDPS></DPS>"
    ).encode("utf-8")
    with pytest.raises(UnsafeXmlError):
        safe_fromstring(payload)


def test_sec_p1_03_billion_laughs_rejected():
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<DPS><infDPS>&lol2;</infDPS></DPS>"""
    with pytest.raises(UnsafeXmlError):
        safe_fromstring(payload)


def test_sec_p1_03_plain_dps_ok():
    root = safe_fromstring(b"<DPS xmlns='http://www.sped.fazenda.gov.br/nfse'><infDPS Id='x'/></DPS>")
    assert root.tag.endswith("DPS") or "DPS" in root.tag



def test_sec_p1_07_retry_on_5xx_then_success():
    client = SefinHttpClient(
        pfx_bytes=b"x",
        pfx_password="",
        max_attempts=3,
        retry_backoff_seconds=0,
    )
    client._mtls = MagicMock(ssl_context=True)
    ok = httpx.Response(201, json={"chaveAcesso": "K"})
    boom = httpx.Response(503, json={"erro": "down"})
    mock_client = MagicMock()
    mock_client.request.side_effect = [boom, ok]
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("integrations.nfse.sefin_client.httpx.Client", return_value=mock_client):
        result = client.emitir_dps(dps_xml=b"<DPS/>")
    assert result.status_code == 201
    assert mock_client.request.call_count == 2


def test_sec_p1_07_no_retry_on_4xx():
    client = SefinHttpClient(
        pfx_bytes=b"x",
        pfx_password="",
        max_attempts=3,
        retry_backoff_seconds=0,
    )
    client._mtls = MagicMock(ssl_context=True)
    bad = httpx.Response(400, json={"erros": [{"codigo": "E001"}]})
    mock_client = MagicMock()
    mock_client.request.return_value = bad
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("integrations.nfse.sefin_client.httpx.Client", return_value=mock_client):
        result = client.emitir_dps(dps_xml=b"<DPS/>")
    assert result.status_code == 400
    assert mock_client.request.call_count == 1


def test_sec_p1_07_retry_exhausted_raises():
    client = SefinHttpClient(
        pfx_bytes=b"x",
        pfx_password="",
        max_attempts=2,
        retry_backoff_seconds=0,
    )
    client._mtls = MagicMock(ssl_context=True)
    boom = httpx.Response(502, json={})
    mock_client = MagicMock()
    mock_client.request.return_value = boom
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("integrations.nfse.sefin_client.httpx.Client", return_value=mock_client):
        with pytest.raises(SefinHttpError, match="502"):
            client.emitir_dps(dps_xml=b"<DPS/>")
    assert mock_client.request.call_count == 2


@pytest.mark.django_db
def test_sec_p1_02_throttle_nf_issue_create(api_client, auth_header, tenant_a, emission_setup):
    from apps.issuance.views import NfIssueWriteThrottle

    cache.clear()
    body = {
        "idempotency_key": "throttle-1",
        "provider_id": str(emission_setup["provider"].id),
        "customer_id": str(emission_setup["customer"].id),
        "service_id": str(emission_setup["service"].id),
        "fiscal_profile_id": str(emission_setup["profile"].id),
        "ibge_code": "3504107",
        "competence_date": "2024-06-15",
        "amount_cents": 2500,
    }
    with patch.object(
        NfIssueWriteThrottle, "THROTTLE_RATES", {"nf_issue_write": "1/min"}
    ):
        first = api_client.post("/api/v1/nf-issue/", body, format="json", **auth_header)
        assert first.status_code == 201
        body["idempotency_key"] = "throttle-2"
        second = api_client.post("/api/v1/nf-issue/", body, format="json", **auth_header)
        assert second.status_code == 429
