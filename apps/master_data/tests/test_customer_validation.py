"""Validação endereço fiscal tomador."""

import pytest

from apps.master_data.customer_validation import (
    normalize_customer_address,
    validate_customer_fiscal_address,
)


def test_normalize_customer_address_sets_ibge_alias():
    addr = normalize_customer_address({"codigo_municipio_ibge": "3504107", "uf": "sp"})
    assert addr["codigo_ibge"] == "3504107"
    assert addr["uf"] == "SP"


def test_validate_customer_fiscal_address_requires_uf_and_ibge():
    with pytest.raises(ValueError, match="UF"):
        validate_customer_fiscal_address({"logradouro": "Rua A"})
    with pytest.raises(ValueError, match="IBGE"):
        validate_customer_fiscal_address({"logradouro": "Rua A", "uf": "SP"})


def test_validate_customer_fiscal_address_ok():
    validate_customer_fiscal_address(
        {"logradouro": "Rua A", "uf": "SP", "codigo_municipio_ibge": "3504107"}
    )
