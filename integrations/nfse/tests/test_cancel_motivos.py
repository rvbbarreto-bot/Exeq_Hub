"""Testes motivos e validação de cancelamento NFS-e."""

import pytest

from integrations.nfse.cancel_motivos import (
    NFSE_CANCEL_JUSTIFICATIVA_MAX,
    NFSE_CANCEL_JUSTIFICATIVA_MIN,
    parse_codigo_cancelamento,
    validate_justificativa,
)


def test_parse_codigo_cancelamento_accepts_official_codes():
    assert parse_codigo_cancelamento("1") == 1
    assert parse_codigo_cancelamento(2) == 2
    assert parse_codigo_cancelamento(9) == 9


def test_parse_codigo_cancelamento_rejects_invalid():
    with pytest.raises(ValueError, match="Selecione"):
        parse_codigo_cancelamento("")
    with pytest.raises(ValueError, match="inválido"):
        parse_codigo_cancelamento("3")


def test_validate_justificativa_bounds():
    ok = "x" * NFSE_CANCEL_JUSTIFICATIVA_MIN
    assert validate_justificativa(ok) == ok
    assert len(validate_justificativa("x" * NFSE_CANCEL_JUSTIFICATIVA_MAX)) == 150
    with pytest.raises(ValueError, match="mínimo"):
        validate_justificativa("curta")
    with pytest.raises(ValueError, match="máximo"):
        validate_justificativa("x" * (NFSE_CANCEL_JUSTIFICATIVA_MAX + 1))
