"""Testes codec SEFIN gzip/base64."""

import pytest

from integrations.nfse.sefin_codec import (
    SefinCodecError,
    gzip_b64_to_xml,
    xml_to_gzip_b64,
)


def test_roundtrip_gzip_b64():
    xml = b'<?xml version="1.0"?><DPS><infDPS Id="1"/></DPS>'
    encoded = xml_to_gzip_b64(xml)
    assert isinstance(encoded, str)
    assert gzip_b64_to_xml(encoded) == xml


def test_xml_to_gzip_b64_rejects_empty():
    with pytest.raises(SefinCodecError):
        xml_to_gzip_b64(b"")


def test_gzip_b64_to_xml_rejects_bad_base64():
    with pytest.raises(SefinCodecError):
        gzip_b64_to_xml("@@@not-base64@@@")


def test_gzip_b64_to_xml_rejects_empty():
    with pytest.raises(SefinCodecError):
        gzip_b64_to_xml("")


def test_gzip_b64_to_xml_rejects_non_gzip_payload():
    import base64

    with pytest.raises(SefinCodecError):
        gzip_b64_to_xml(base64.b64encode(b"not-gzip").decode())
