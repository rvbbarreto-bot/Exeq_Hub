"""Porta de consulta cadastral (CNPJ) — separada de DAS/DARF SERPRO."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class CadastralAddress:
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cep: str = ""
    municipio: str = ""
    uf: str = ""
    codigo_municipio_ibge: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "logradouro": self.logradouro,
            "numero": self.numero,
            "complemento": self.complemento,
            "bairro": self.bairro,
            "cep": self.cep,
            "municipio": self.municipio,
            "uf": self.uf,
            "codigo_municipio_ibge": self.codigo_municipio_ibge,
        }


@dataclass(frozen=True)
class CadastralLookupResult:
    document: str
    legal_name: str
    trade_name: str = ""
    situacao_cadastral: str = ""
    data_abertura: date | None = None
    natureza_juridica: str = ""
    cnae_principal: str = ""
    cnaes_secundarios: list[str] = field(default_factory=list)
    porte: str = ""
    optante_simples: bool | None = None
    optante_mei: bool | None = None
    telefone: str = ""
    email: str = ""
    address: CadastralAddress = field(default_factory=CadastralAddress)
    raw: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    provider_kind: str = ""

    def as_api_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "legal_name": self.legal_name,
            "trade_name": self.trade_name,
            "situacao_cadastral": self.situacao_cadastral,
            "data_abertura": self.data_abertura.isoformat() if self.data_abertura else None,
            "natureza_juridica": self.natureza_juridica,
            "cnae_principal": self.cnae_principal,
            "cnaes_secundarios": list(self.cnaes_secundarios),
            "porte": self.porte,
            "optante_simples": self.optante_simples,
            "optante_mei": self.optante_mei,
            "telefone": self.telefone,
            "email": self.email,
            "address": self.address.as_dict(),
            "cached": self.cached,
            "provider_kind": self.provider_kind,
            "raw": self.raw,
        }


class CadastroGateway(Protocol):
    kind: str

    def lookup_cnpj(self, *, cnpj: str) -> CadastralLookupResult: ...
