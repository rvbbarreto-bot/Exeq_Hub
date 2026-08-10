"""U5-CCE / U14 — Carta de Correção 110110 (stub + domínio + API)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.artifacts import has_xml_cce
from apps.nfe.exceptions import NfeValidationError
from apps.nfe.models import NfeArtifact, NfeInvoice
from apps.nfe.services import (
    allowed_actions,
    create_draft,
    create_product,
    emit_invoice,
    issue_carta_correcao,
    replace_items,
)
from integrations.sefaz_nfe.evento_cce import (
    NfeCceBuildError,
    build_cce_env_evento_xml,
)
from integrations.sefaz_nfe.parse import AutorizacaoParse
from integrations.sefaz_nfe.port import HttpNfeProvider, NfeEmitResult, StubNfeProvider
from integrations.sefaz_nfe.transport import SefazHttpResponse

_KEY = "35260837229907000137550010000000011000000010"
_CORR = "Correcao do endereco de entrega do destinatario na nota fiscal."


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av T",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


def _emit_authorized(tenant, provider, customer, key="cce-1"):
    product = create_product(
        tenant=tenant,
        code=f"CCE-{key[:6]}",
        description="Item CCe",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key=key,
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    return emit_invoice(inv)


def test_build_cce_xml():
    raw = build_cce_env_evento_xml(
        access_key=_KEY,
        cnpj="37229907000137",
        x_correcao=_CORR,
        tp_amb="2",
        n_seq=2,
    )
    text = raw.decode("utf-8")
    assert "110110" in text
    assert "Carta de Correcao" in text
    assert _CORR in text
    assert "ID110110" in text
    assert ">2</" in text or "nSeqEvento>2" in text


def test_build_cce_short_text():
    with pytest.raises(NfeCceBuildError):
        build_cce_env_evento_xml(
            access_key=_KEY,
            cnpj="37229907000137",
            x_correcao="curto",
        )


def test_stub_cce_builds_xml():
    r = StubNfeProvider().carta_correcao(
        access_key=_KEY,
        x_correcao=_CORR,
        context={"cnpj": "37229907000137", "tp_amb": "2", "n_seq_evento": 1},
    )
    assert r.status == "accepted"
    assert r.signed_xml is not None
    assert b"110110" in r.signed_xml


@pytest.mark.django_db
def test_http_cce_mock_cstat_135(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    ok = SefazHttpResponse(
        http_status=200,
        body="<ok/>",
        c_stat="135",
        x_motivo="Evento registrado e vinculado a NF-e",
        protocol="135260000000888",
        access_key=_KEY,
        lote_c_stat="128",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "pwd")),
        patch(
            "integrations.sefaz_nfe.port.sign_evento_nfe_xml",
            return_value=b"<signed/>",
            create=True,
        ),
        patch(
            "integrations.sefaz_nfe.sign.sign_evento_nfe_xml",
            return_value=b"<signed-cce/>",
        ),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_evento",
            return_value=ok,
        ),
    ):
        r = HttpNfeProvider().carta_correcao(
            access_key=_KEY,
            x_correcao=_CORR,
            context={
                "tenant": tenant_a,
                "cnpj": "37229907000137",
                "tp_amb": "2",
                "uf": "SP",
                "n_seq_evento": 1,
            },
        )
    assert r.status == "accepted"
    assert r.protocol == "135260000000888"


@pytest.mark.django_db
def test_domain_cce_stub_stores_xml(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _emit_authorized(tenant_a, provider_sp, customer_b2b, "cce-dom-1")
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert "cce" in allowed_actions(inv)

    issue_carta_correcao(inv, x_correcao=_CORR)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert has_xml_cce(inv)
    assert inv.last_validation.get("cce_n_seq") == 1
    assert "download_cce" in allowed_actions(inv)


@pytest.mark.django_db
def test_domain_cce_seq_increments(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _emit_authorized(tenant_a, provider_sp, customer_b2b, "cce-dom-2")
    issue_carta_correcao(inv, x_correcao=_CORR + " sequencia um.")
    inv.refresh_from_db()
    issue_carta_correcao(inv, x_correcao=_CORR + " sequencia dois.")
    inv.refresh_from_db()
    assert inv.last_validation.get("cce_n_seq") == 2
    assert NfeArtifact.objects.filter(
        invoice=inv, kind=NfeArtifact.Kind.XML_CCE
    ).count() == 1


@pytest.mark.django_db
def test_domain_cce_reject_raises(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _emit_authorized(tenant_a, provider_sp, customer_b2b, "cce-dom-3")
    with patch.object(
        StubNfeProvider,
        "carta_correcao",
        return_value=NfeEmitResult(
            status="rejected",
            rejection_code="573",
            rejection_message="Duplicidade de evento",
            raw={"mode": "stub"},
        ),
    ):
        with pytest.raises(NfeValidationError):
            issue_carta_correcao(inv, x_correcao=_CORR)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert not has_xml_cce(inv)


@pytest.mark.django_db
def test_api_cce(
    api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _emit_authorized(tenant_a, provider_sp, customer_b2b, "cce-api-1")
    url = reverse("nfe-invoice-cce", kwargs={"pk": inv.id})
    res = api_client.post(url, {"x_correcao": _CORR}, format="json", **auth_header)
    assert res.status_code == 200, res.data
    assert res.data["status"] == "authorized"
    assert res.data["artifacts"]["xml_cce"] is True
    assert "download_cce" in res.data["allowed_actions"]

    dl = api_client.get(
        reverse("nfe-invoice-cce-xml", kwargs={"pk": inv.id}), **auth_header
    )
    assert dl.status_code == 200
    assert b"110110" in dl.content or b"Carta" in dl.content
