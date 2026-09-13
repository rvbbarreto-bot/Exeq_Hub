"""Porta de pagamento Food — adapters por provedor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FoodPaymentIntentResult:
    provider_payment_id: str = ""
    pix_copy_paste: str = ""
    gateway_payload: dict | None = None


@runtime_checkable
class FoodPaymentProvider(Protocol):
    kind: str

    def create_payment_intent(
        self,
        *,
        tenant,
        order_id,
        method: str = "pix",
        due_date=None,
    ): ...
