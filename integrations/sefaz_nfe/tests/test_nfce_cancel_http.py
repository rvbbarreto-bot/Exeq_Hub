"""NFC-e cancel HTTP — endpoint SP homolog (mock)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from integrations.sefaz_nfe.port import HttpNfeProvider
from integrations.sefaz_nfe.transport import SefazHttpResponse

_CANCEL_OK = """<?xml version="1.0" encoding="UTF-8"?>
<retEnvEvento versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <tpAmb>2</tpAmb>
  <cStat>128</cStat>
  <xMotivo>Evento registrado</xMotivo>
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>2</tpAmb>
      <cStat>135</cStat>
      <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
      <chNFe>35260837229907000137650010000000011000000010</chNFe>
      <nProt>135260000000002</nProt>
    </infEvento>
  </retEvento>
</retEnvEvento>
"""


def _passthrough_evento(env_evento_xml, pfx_bytes, password=""):
    raw = env_evento_xml if isinstance(env_evento_xml, (bytes, bytearray)) else str(env_evento_xml).encode()
    return raw


@pytest.mark.django_db
def test_nfce_cancel_http_uses_sp_endpoint(settings, tenant_a):
    settings.NFCE_HTTP_DRY_RUN = False
    key = "35260837229907000137650010000000011000000010"
    posted: dict = {}

    def _capture(*, url, evento_xml, pfx_bytes, password="", timeout=60.0):
        posted["url"] = url
        return SefazHttpResponse(
            http_status=200,
            body=_CANCEL_OK,
            c_stat="135",
            x_motivo="Evento registrado",
            protocol="135260000000002",
            access_key=key,
        )

    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch(
            "integrations.sefaz_nfe.evento_cancel.build_cancel_from_context",
            return_value=b"<envEvento/>",
        ),
        patch("integrations.sefaz_nfe.sign.sign_evento_nfe_xml", side_effect=_passthrough_evento),
        patch("integrations.sefaz_nfe.transport.post_nfe_evento", side_effect=_capture),
    ):
        r = HttpNfeProvider().cancelar(
            access_key=key,
            justificativa="Cancelamento homolog teste PDV",
            context={
                "tenant": tenant_a,
                "protocol": "135260000000001",
                "tp_amb": "2",
                "uf": "SP",
                "document_model": "65",
            },
        )

    assert r.status == "cancelled"
    assert posted["url"] == (
        "https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeRecepcaoEvento4.asmx"
    )
