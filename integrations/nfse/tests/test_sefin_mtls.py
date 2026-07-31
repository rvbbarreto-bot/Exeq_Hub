"""Testes mTLS SEFIN (contexto SSL a partir de PFX)."""

import tempfile
from pathlib import Path

import pytest

from integrations.nfse.sefin_mtls import SefinMtlsError, build_sefin_mtls_context
from integrations.nfse.tests.pfx_factory import make_test_pfx


def test_build_sefin_mtls_context_ok():
    pfx = make_test_pfx(password="segredo")
    material = build_sefin_mtls_context(pfx_bytes=pfx, password="segredo")
    try:
        assert material.ssl_context is not None
        assert material.ssl_context.check_hostname is True
    finally:
        material.close()


def test_build_sefin_mtls_cleans_pem_from_disk(monkeypatch):
    """SEC-P2-06: PEM some do disco imediatamente após load_cert_chain."""
    created: list[str] = []
    real_td = tempfile.TemporaryDirectory

    class TrackingTD(real_td):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self.name)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", TrackingTD)
    pfx = make_test_pfx(password="x")
    material = build_sefin_mtls_context(pfx_bytes=pfx, password="x")
    try:
        assert created
        assert all(not Path(p).exists() for p in created)
        assert material.ssl_context is not None
    finally:
        material.close()


def test_build_sefin_mtls_context_wrong_password():
    pfx = make_test_pfx(password="certo")
    with pytest.raises(SefinMtlsError):
        build_sefin_mtls_context(pfx_bytes=pfx, password="errado")


def test_build_sefin_mtls_context_invalid_bytes():
    with pytest.raises(SefinMtlsError):
        build_sefin_mtls_context(pfx_bytes=b"not-a-pfx", password="")
