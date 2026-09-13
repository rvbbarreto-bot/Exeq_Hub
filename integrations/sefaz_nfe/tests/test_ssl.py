"""Verificação TLS SEFAZ — bundle ICP-Brasil."""

from pathlib import Path

import pytest
from django.test import override_settings

from integrations.sefaz_nfe.ssl import sefaz_requests_verify

_BUNDLED = Path(__file__).resolve().parents[1] / "certs" / "icp-brasil-sefaz.pem"


def test_sefaz_requests_verify_uses_bundled_ca_by_default():
    assert sefaz_requests_verify() == str(_BUNDLED)
    assert _BUNDLED.is_file()


@override_settings(NFE_SEFAZ_CA_BUNDLE="/custom/ca.pem")
def test_sefaz_requests_verify_env_override():
    assert sefaz_requests_verify() == "/custom/ca.pem"
