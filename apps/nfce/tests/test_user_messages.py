"""Mensagens amigáveis NFC-e."""

from apps.nfce.user_messages import (
    format_nfce_emit_exception,
    format_nfce_gate_errors,
    format_nfce_rejection_message,
    format_nfce_validation_errors,
)


def test_format_nfce_gate_csc_friendly():
    failed = [{"id": "csc", "ok": False, "label": "CSC não cadastrado", "must": True}]
    msg = format_nfce_gate_errors(failed)
    assert "contador" in msg.lower()
    assert "CSC" in msg
    assert "CSC não cadastrado" not in msg
    assert "[" not in msg


def test_format_nfce_gate_csc_priority_over_series():
    failed = [
        {"id": "csc", "ok": False, "label": "CSC não cadastrado", "must": True},
        {"id": "series", "ok": False, "label": "Série 1/1 auto-criada (stub)", "must": True},
    ]
    msg = format_nfce_gate_errors(failed)
    assert "contador" in msg.lower()
    assert "stub" not in msg.lower()


def test_format_nfce_validation_ie_hint():
    errors = [{"field": "provider.state_registration", "message": "IE obrigatória"}]
    msg = format_nfce_validation_errors(errors)
    assert "Inscrição Estadual" in msg
    assert "Isento" in msg


def test_format_nfce_rejection_legacy_ssl():
    legacy = (
        "Falha HTTP SEFAZ NFC-e: HTTPSConnectionPool(host='nfce.fazenda.sp.gov.br', port=443): "
        "Max retries exceeded (Caused by SSLError(SSLCertVerificationError(1, "
        "'[SSL: CERTIFICATE_VERIFY_FAILED]')))"
    )
    msg = format_nfce_rejection_message("HTTP", legacy)
    assert "ICP-Brasil" in msg
    assert "HTTPSConnectionPool" not in msg


def test_format_nfce_emit_exception_ssl_raw():
    exc = Exception(
        "HTTPSConnectionPool(host='nfce.fazenda.sp.gov.br'): SSLCertVerificationError"
    )
    msg = format_nfce_emit_exception(exc)
    assert "SEFAZ" in msg
    assert "HTTPSConnectionPool" not in msg
