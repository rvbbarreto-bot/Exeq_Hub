"""Porta PaymentGateway — Asaas (default) / futuros gateways."""

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class ChargeRegisterResult:
    external_ref: str
    status: str
    raw: dict[str, Any]


class PaymentGateway(Protocol):
    kind: str

    def registrar_cobranca(
        self,
        *,
        amount_cents: int,
        due_date: date,
        description: str,
        customer_document: str,
        customer_name: str,
        external_reference: str,
        idempotency_key: str,
    ) -> ChargeRegisterResult: ...

    def cancelar(self, *, ref: str) -> ChargeRegisterResult: ...
