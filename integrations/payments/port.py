"""Porta PaymentGateway — Inter (default) / Asaas / C6."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class ChargeRegisterResult:
    external_ref: str
    status: str
    raw: dict[str, Any]
    billing_type: str = "BOLETO"
    payment_url: str = ""
    digitable_line: str = ""
    barcode: str = ""
    boleto_pdf_url: str = ""
    pix_copy_paste: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


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
        customer_address: dict[str, Any] | None = None,
        customer_email: str = "",
        charge_options: dict[str, Any] | None = None,
    ) -> ChargeRegisterResult: ...

    def cancelar(
        self, *, ref: str, motivo_cancelamento: str | None = None
    ) -> ChargeRegisterResult: ...

    def consultar_cobranca(self, *, ref: str) -> ChargeRegisterResult: ...

    def baixar_pdf(self, *, ref: str) -> bytes: ...
