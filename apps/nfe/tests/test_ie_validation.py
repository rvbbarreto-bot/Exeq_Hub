"""IE emitente — validação unificada gate/tax/XML."""

from __future__ import annotations

import pytest

from apps.nfe.gate import build_gate_payload


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    return settings

from apps.nfe.ie_validation import (
    emitter_ie_error,
    normalize_emitter_ie_for_xml,
    validate_emitter_ie,
)


@pytest.mark.parametrize(
    "ie,http,ok",
    [
        ("", False, True),
        ("", True, False),
        ("ISENTO", True, True),
        ("123456789112", True, True),
        ("X", True, False),
    ],
)
def test_validate_emitter_ie(ie, http, ok):
    result, _ = validate_emitter_ie(ie, http_mode=http)
    assert result is ok


def test_emitter_ie_error_message():
    assert emitter_ie_error("", http_mode=True) is not None
    assert emitter_ie_error("123456789112", http_mode=True) is None


def test_normalize_emitter_ie_production_requires_value():
    with pytest.raises(ValueError, match="obrigatória"):
        normalize_emitter_ie_for_xml("", tp_amb="1")


def test_normalize_emitter_ie_homolog_fallback():
    assert normalize_emitter_ie_for_xml("", tp_amb="2") == "ISENTO"


@pytest.mark.django_db
def test_gate_http_rejects_empty_ie(nfe_settings, tenant_a, provider_sp, settings):
    settings.NFE_HTTP_MODE = "http"
    provider_sp.state_registration = ""
    provider_sp.save(update_fields=["state_registration"])
    payload = build_gate_payload(tenant=tenant_a)
    ie_chk = next(c for c in payload["checks"] if c["id"] == "ie")
    assert ie_chk["ok"] is False
