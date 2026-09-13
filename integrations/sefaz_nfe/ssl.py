"""Verificação TLS SEFAZ — cadeia ICP-Brasil (NFe/NFC-e)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

_BUNDLED_CA = Path(__file__).resolve().parent / "certs" / "icp-brasil-sefaz.pem"


def sefaz_requests_verify() -> str | bool:
    """
    Caminho CA para `requests`/`urllib3` ao chamar webservices SEFAZ.

    Ordem: NFE_SEFAZ_CA_BUNDLE (env) → bundle ICP-Brasil do repo → certifi.
    """
    override = (getattr(settings, "NFE_SEFAZ_CA_BUNDLE", None) or "").strip()
    if override:
        return override
    if _BUNDLED_CA.is_file():
        return str(_BUNDLED_CA)
    try:
        import certifi

        return certifi.where()
    except ImportError:
        return True
