"""Motor de roteamento fiscal PDV — NFC-e 65 vs NF-e 55."""

from __future__ import annotations

from apps.fiscal.document_policy.registry import get_policy
from apps.fiscal.document_policy.types import DocumentRoute, SaleContext


def resolve_document_route(ctx: SaleContext) -> DocumentRoute:
    policy = get_policy(ctx.uf)
    return policy.evaluate(ctx)
