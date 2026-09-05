"""Registry de políticas por UF — extensível sem if espalhado."""

from __future__ import annotations

from typing import Protocol

from apps.fiscal.document_policy.default_policy import DefaultDocumentPolicy
from apps.fiscal.document_policy.sp_policy import SpDocumentPolicy
from apps.fiscal.document_policy.types import DocumentRoute, SaleContext


class FiscalDocumentPolicy(Protocol):
    uf: str

    def evaluate(self, ctx: SaleContext) -> DocumentRoute: ...


_REGISTRY: dict[str, FiscalDocumentPolicy] = {
    "SP": SpDocumentPolicy(),
    "DEFAULT": DefaultDocumentPolicy(),
}


def get_policy(uf: str) -> FiscalDocumentPolicy:
    key = (uf or "").upper().strip()
    return _REGISTRY.get(key, _REGISTRY["DEFAULT"])
