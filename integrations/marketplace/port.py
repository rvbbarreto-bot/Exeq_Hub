"""Marketplace Food — porta HTTP (iFood / aiqfome)."""

from __future__ import annotations

from typing import Any, Protocol


class MarketplaceGateway(Protocol):
    provider: str

    def fetch_orders(self, *, merchant_ref: str) -> list[dict[str, Any]]:
        """Lista pedidos novos/abertos no marketplace (payload bruto)."""
        ...
