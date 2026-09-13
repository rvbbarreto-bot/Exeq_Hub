"""Fase 3 — logo emitente no DANFE."""

from __future__ import annotations

import base64

import pytest

from apps.nfe.danfe_logo import resolve_provider_logo_bytes

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_resolve_logo_from_address_path(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(_TINY_PNG)

    class _Provider:
        document = "37229907000137"
        address = {"danfe_logo_path": str(logo)}

    assert resolve_provider_logo_bytes(_Provider()) == _TINY_PNG


def test_resolve_logo_from_logo_dir(settings, tmp_path):
    settings.NFE_DANFE_LOGO_DIR = str(tmp_path)
    (tmp_path / "61536366000174.png").write_bytes(_TINY_PNG)

    class _Provider:
        document = "61536366000174"
        address = {}

    assert resolve_provider_logo_bytes(_Provider()) == _TINY_PNG


def test_resolve_logo_none_without_config():
    class _Provider:
        document = "37229907000137"
        address = {}

    assert resolve_provider_logo_bytes(_Provider()) is None
