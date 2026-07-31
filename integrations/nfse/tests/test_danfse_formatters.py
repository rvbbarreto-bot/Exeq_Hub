"""Testes formatação pt-BR DANFSe."""

from integrations.nfse.danfse.formatters import (
    format_cep,
    format_competencia,
    format_datetime_br,
    format_document,
    format_money_br,
    format_percent_br,
)


def test_format_document_cnpj_cpf():
    assert format_document("37229907000137") == "37.229.907/0001-37"
    assert format_document("26391118841") == "263.911.188-41"
    assert format_document("—") == "—"


def test_format_cep_and_money_percent():
    assert format_cep("12943480") == "12943-480"
    assert format_money_br("1411.00") == "R$ 1.411,00"
    assert format_money_br("15.00") == "R$ 15,00"
    assert format_money_br("—") == "—"
    assert format_percent_br("6.00") == "6,00%"


def test_format_datetime_and_competencia():
    assert format_datetime_br("2026-07-30T19:35:25-03:00") == "30/07/2026 19:35:25"
    assert format_datetime_br("2026-07-30T19:35:20") == "30/07/2026 19:35:20"
    assert format_competencia("2026-07-29") == "07/2026"
    assert format_competencia("2026-07") == "07/2026"
