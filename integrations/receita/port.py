"""Porta Receita Federal — DAS/DARF."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class GuiaCapturaResult:
    valor_principal: Decimal
    valor_multa: Decimal
    valor_juros: Decimal
    linha_digitavel: str
    pix_copia_cola: str
    compliance_status: str
    compliance_motivo: str
    data_vencimento: str | None = None
    pdf_bytes: bytes = b""
    raw: dict | None = None


class ReceitaGateway(Protocol):
    kind: str

    def capturar_das(self, *, cnpj: str, competencia: str) -> GuiaCapturaResult: ...

    def capturar_darf(self, *, cnpj: str, competencia: str) -> GuiaCapturaResult: ...
