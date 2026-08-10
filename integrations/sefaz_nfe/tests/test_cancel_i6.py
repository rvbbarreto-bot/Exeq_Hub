"""I6 — cancelamento NF-e evento 110111 (build + mock HTTP + stub lab)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.artifacts import has_artifact
from apps.nfe.models import NfeArtifact
from apps.nfe.services import (
    cancel_invoice,
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
)
from integrations.sefaz_nfe.evento_cancel import (
    NfeEventoBuildError,
    build_cancel_env_evento_xml,
    build_inf_evento_id,
)
from integrations.sefaz_nfe.parse import map_cstat_to_status, parse_evento_response
from integrations.sefaz_nfe.port import HttpNfeProvider, StubNfeProvider
from integrations.sefaz_nfe.transport import SefazHttpResponse

_KEY = "35260837229907000137550010000000011000000010"
_JUST = "Cancelamento de teste em homologacao com mais de 15 chars"

_FIXTURE_CANCEL_OK = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
      <retEnvEvento versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
        <idLote>1</idLote>
        <tpAmb>2</tpAmb>
        <cStat>128</cStat>
        <xMotivo>Lote de Evento Processado</xMotivo>
        <retEvento versao="1.00">
          <infEvento>
            <tpAmb>2</tpAmb>
            <verAplic>SP</verAplic>
            <cOrgao>35</cOrgao>
            <cStat>135</cStat>
            <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
            <chNFe>35260837229907000137550010000000011000000010</chNFe>
            <tpEvento>110111</tpEvento>
            <nSeqEvento>1</nSeqEvento>
            <nProt>135260000000777</nProt>
          </infEvento>
        </retEvento>
      </retEnvEvento>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>
"""

_FIXTURE_CANCEL_REJ = """<?xml version="1.0" encoding="UTF-8"?>
<retEnvEvento versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <cStat>128</cStat>
  <xMotivo>Lote de Evento Processado</xMotivo>
  <retEvento versao="1.00">
    <infEvento>
      <cStat>501</cStat>
      <xMotivo>Rejeicao: Prazo de cancelamento superior ao previsto na Legislaçao</xMotivo>
      <chNFe>35260837229907000137550010000000011000000010</chNFe>
      <tpEvento>110111</tpEvento>
    </infEvento>
  </retEvento>
</retEnvEvento>
"""


def test_build_inf_evento_id():
    eid = build_inf_evento_id(access_key=_KEY, n_seq=1)
    assert eid.startswith("ID110111")
    assert eid.endswith("01")
    assert len(eid) == 2 + 6 + 44 + 2


def test_build_cancel_evento_xml():
    raw = build_cancel_env_evento_xml(
        access_key=_KEY,
        cnpj="37229907000137",
        protocol="135260000000001",
        justificativa=_JUST,
        tp_amb="2",
        dh_evento=datetime(2026, 8, 5, 12, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )
    text = raw.decode("utf-8")
    assert "envEvento" in text
    assert "tpEvento" in text
    assert "110111" in text
    assert "Cancelamento" in text
    assert _JUST in text
    assert "ID110111" in text


def test_build_cancel_justificativa_curta():
    with pytest.raises(NfeEventoBuildError):
        build_cancel_env_evento_xml(
            access_key=_KEY,
            cnpj="37229907000137",
            protocol="1",
            justificativa="curto",
        )


def test_parse_evento_prefers_inf_not_lote_128():
    p = parse_evento_response(_FIXTURE_CANCEL_OK)
    assert p.c_stat == "135"
    assert p.lote_c_stat == "128"
    assert p.protocol == "135260000000777"
    assert map_cstat_to_status(p.c_stat) == "cancelled"


def test_parse_evento_rejeicao():
    p = parse_evento_response(_FIXTURE_CANCEL_REJ)
    assert p.c_stat == "501"
    assert map_cstat_to_status(p.c_stat) == "rejected"


def test_stub_cancel_builds_xml():
    r = StubNfeProvider().cancelar(
        access_key=_KEY,
        justificativa=_JUST,
        context={"protocol": "135260000000001", "cnpj": "37229907000137", "tp_amb": "2"},
    )
    assert r.status == "cancelled"
    assert r.signed_xml is not None
    assert b"110111" in r.signed_xml


@pytest.mark.django_db
def test_http_cancel_mock_cstat_135(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    ok = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_CANCEL_OK,
        c_stat="135",
        x_motivo="Evento registrado e vinculado a NF-e",
        protocol="135260000000777",
        access_key=_KEY,
        lote_c_stat="128",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch(
            "integrations.sefaz_nfe.sign.sign_evento_nfe_xml",
            side_effect=lambda **kw: kw["env_evento_xml"]
            if isinstance(kw["env_evento_xml"], (bytes, bytearray))
            else str(kw["env_evento_xml"]).encode(),
        ),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_evento",
            return_value=ok,
        ) as post_mock,
    ):
        r = HttpNfeProvider().cancelar(
            access_key=_KEY,
            justificativa=_JUST,
            context={
                "tenant": tenant_a,
                "protocol": "135260000000001",
                "cnpj": "37229907000137",
                "tp_amb": "2",
                "uf": "SP",
            },
        )
    post_mock.assert_called_once()
    assert r.status == "cancelled"
    assert r.protocol == "135260000000777"
    assert r.signed_xml is not None
    assert r.raw and r.raw.get("cStat") == "135"
    assert "password" not in (r.raw or {})


@pytest.mark.django_db
def test_http_cancel_mock_reject_stays_failed_status(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    bad = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_CANCEL_REJ,
        c_stat="501",
        x_motivo="Prazo",
        protocol="",
        access_key=_KEY,
        lote_c_stat="128",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch(
            "integrations.sefaz_nfe.sign.sign_evento_nfe_xml",
            side_effect=lambda **kw: b"<envEvento/>",
        ),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_evento",
            return_value=bad,
        ),
    ):
        r = HttpNfeProvider().cancelar(
            access_key=_KEY,
            justificativa=_JUST,
            context={
                "tenant": tenant_a,
                "protocol": "135260000000001",
                "cnpj": "37229907000137",
            },
        )
    assert r.status == "rejected"
    assert r.rejection_code == "501"


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
        address={
            "logradouro": "Rua Jose Florido",
            "numero": "121",
            "bairro": "Jardim Alvinopolis",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente B2B",
        address={
            "logradouro": "Av Teste",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_domain_cancel_stub_stores_xml_cancel(nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="SKU-C",
        description="Produto cancel",
        ncm="21069090",
        unit_price_cents=2000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="cancel-i6-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == "authorized"

    cancel_invoice(inv, justificativa=_JUST)
    inv.refresh_from_db()
    assert inv.status == "cancelled"
    assert has_artifact(inv, NfeArtifact.Kind.XML_CANCEL)


@pytest.mark.django_db
def test_domain_cancel_http_reject_keeps_authorized(
    nfe_settings, tenant_a, provider_sp, customer_b2b, settings
):
    settings.NFE_HTTP_MODE = "http"
    product = create_product(
        tenant=tenant_a,
        code="SKU-C2",
        description="Produto",
        ncm="21069090",
        unit_price_cents=2000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="cancel-i6-reject",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    # emit em stub path is easier: authorize first with stub then switch?
    # Emit with stub then force http cancel
    settings.NFE_HTTP_MODE = "stub"
    emit_invoice(inv)
    inv.refresh_from_db()
    settings.NFE_HTTP_MODE = "http"
    settings.NFE_HTTP_DRY_RUN = False

    bad = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_CANCEL_REJ,
        c_stat="501",
        x_motivo="Prazo",
        protocol="",
        access_key=inv.access_key,
        lote_c_stat="128",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch(
            "integrations.sefaz_nfe.sign.sign_evento_nfe_xml",
            side_effect=lambda **kw: b"<envEvento/>",
        ),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_evento",
            return_value=bad,
        ),
    ):
        out = cancel_invoice(inv, justificativa=_JUST)
    assert out.status == "authorized"
    assert "Prazo" in (out.rejection_message or "") or out.rejection_code == "501"
