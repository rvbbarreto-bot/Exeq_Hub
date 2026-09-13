"""Política SP — parâmetros UF pivot (homolog)."""

from __future__ import annotations

from apps.fiscal.document_policy.default_policy import DefaultDocumentPolicy, evaluate_sale
from apps.fiscal.document_policy.types import DocumentRoute, SaleContext


class SpDocumentPolicy(DefaultDocumentPolicy):
    uf = "SP"

    def evaluate(self, ctx: SaleContext) -> DocumentRoute:
        return evaluate_sale(ctx)
