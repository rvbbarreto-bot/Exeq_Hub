"""Mensagens amigáveis — transporte HTTP SEFAZ."""

from integrations.sefaz_nfe.messages import format_sefaz_http_rejection, format_sefaz_transport_error

_LEGACY_SSL = (
    "Falha HTTP SEFAZ NFC-e: HTTPSConnectionPool(host='nfce.fazenda.sp.gov.br', port=443): "
    "Max retries exceeded with url: /ws/NFeAutorizacao4.asmx "
    "(Caused by SSLError(SSLCertVerificationError(1, "
    "'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
    "unable to get local issuer certificate (_ssl.c:1010)')))"
)

_FRIENDLY_SSL = (
    "Não foi possível conectar com segurança à SEFAZ (nfce.fazenda.sp.gov.br): "
    "falha na validação do certificado do servidor (cadeia ICP-Brasil). "
    "Peça ao responsável técnico para atualizar a cadeia de certificados "
    "ICP-Brasil v10 no servidor ou informe o suporte EXEQ."
)


def test_format_sefaz_transport_ssl_error():
    exc = Exception(_LEGACY_SSL.split(":", 1)[-1].strip())
    msg = format_sefaz_transport_error(exc, document_label="NFC-e")
    assert "ICP-Brasil" in msg
    assert "nfce.fazenda.sp.gov.br" in msg
    assert "HTTPSConnectionPool" not in msg
    assert "SSLCertVerificationError" not in msg


def test_format_sefaz_http_rejection_legacy_ssl():
    msg = format_sefaz_http_rejection("HTTP", _LEGACY_SSL, document_label="NFC-e")
    assert msg == _FRIENDLY_SSL


def test_format_sefaz_http_rejection_keeps_friendly_message():
    msg = format_sefaz_http_rejection("HTTP", _FRIENDLY_SSL, document_label="NFC-e")
    assert msg == _FRIENDLY_SSL


def test_format_sefaz_http_rejection_sefaz_motivo():
    msg = format_sefaz_http_rejection("539", "Duplicidade de NF-e", document_label="NFC-e")
    assert msg == "Duplicidade de NF-e"
