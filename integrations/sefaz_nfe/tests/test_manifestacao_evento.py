"""Build XML manifestação destinatário."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from integrations.sefaz_nfe.evento_cancel import NfeEventoBuildError
from integrations.sefaz_nfe.manifestacao.evento import (
    TP_EVENTO_CIENCIA,
    TP_EVENTO_CONFIRMACAO,
    TP_EVENTO_NAO_REALIZADA,
    build_manifest_env_evento_xml,
)

_KEY = "35260111222333000181550010000000011234567890"


def test_build_ciencia_evento():
    raw = build_manifest_env_evento_xml(
        access_key=_KEY,
        cnpj="37229907000137",
        tp_evento=TP_EVENTO_CIENCIA,
        tp_amb="2",
        dh_evento=datetime(2026, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )
    text = raw.decode("utf-8")
    assert "210210" in text
    assert "Ciencia da Emissao" in text
    assert "ID210210" in text
    assert "37229907000137" in text


def test_build_confirmacao_evento():
    raw = build_manifest_env_evento_xml(
        access_key=_KEY,
        cnpj="37229907000137",
        tp_evento=TP_EVENTO_CONFIRMACAO,
    )
    assert b"210200" in raw
    assert b"Confirmacao da Operacao" in raw


def test_build_nao_realizada_requires_just():
    with pytest.raises(NfeEventoBuildError):
        build_manifest_env_evento_xml(
            access_key=_KEY,
            cnpj="37229907000137",
            tp_evento=TP_EVENTO_NAO_REALIZADA,
            justificativa="curta",
        )

    raw = build_manifest_env_evento_xml(
        access_key=_KEY,
        cnpj="37229907000137",
        tp_evento=TP_EVENTO_NAO_REALIZADA,
        justificativa="Operacao nao realizada por divergencia comercial na entrega",
    )
    assert b"xJust" in raw
