"""Tipos da política de roteamento NFC-e ↔ NF-e (LLR NFC-e §3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DocumentModel(str, Enum):
    NFCE = "65"
    NFE = "55"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SaleContext:
    uf: str
    total_cents: int
    cpf: str | None = None
    cnpj: str | None = None
    delivery: bool = False
    installment: bool = False


@dataclass(frozen=True)
class DocumentRoute:
    model: DocumentModel
    omit_dest: bool = False
    errors: tuple[dict[str, str], ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.model != DocumentModel.BLOCKED and not self.errors
