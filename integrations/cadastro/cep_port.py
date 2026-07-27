"""Consulta de CEP — porta separada da consulta CNPJ."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class CepLookupResult:
    cep: str
    logradouro: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    codigo_municipio_ibge: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    provider_kind: str = ""

    def as_api_dict(self) -> dict[str, Any]:
        return {
            "cep": self.cep,
            "logradouro": self.logradouro,
            "bairro": self.bairro,
            "municipio": self.municipio,
            "uf": self.uf,
            "codigo_municipio_ibge": self.codigo_municipio_ibge,
            "provider_kind": self.provider_kind,
            "raw": self.raw,
        }


class CepGateway(Protocol):
    kind: str

    def lookup_cep(self, *, cep: str) -> CepLookupResult: ...
