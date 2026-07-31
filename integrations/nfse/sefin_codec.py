"""Codec gzip+base64 do envelope SEFIN (dpsXmlGZipB64 / nfseXmlGZipB64)."""

from __future__ import annotations

import base64
import gzip


class SefinCodecError(ValueError):
    pass


def xml_to_gzip_b64(xml_bytes: bytes) -> str:
    if not xml_bytes:
        raise SefinCodecError("XML vazio para compactação SEFIN")
    compressed = gzip.compress(xml_bytes)
    return base64.b64encode(compressed).decode("ascii")


def gzip_b64_to_xml(payload: str | bytes) -> bytes:
    if payload is None or payload == "":
        raise SefinCodecError("Payload gzip/base64 vazio")
    raw = payload.encode("ascii") if isinstance(payload, str) else payload
    try:
        compressed = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise SefinCodecError("Base64 inválido no envelope SEFIN") from exc
    try:
        return gzip.decompress(compressed)
    except Exception as exc:  # noqa: BLE001
        raise SefinCodecError("Gzip inválido no envelope SEFIN") from exc
