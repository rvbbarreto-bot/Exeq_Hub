"""Clientes HTTP iFood / aiqfome (modo stub | http)."""

from __future__ import annotations

from typing import Any

import requests
from django.conf import settings

from integrations.marketplace.errors import MarketplaceConfigError, MarketplaceHttpError


def _timeout() -> float:
    return float(getattr(settings, "MARKETPLACE_HTTP_TIMEOUT", 15) or 15)


def _http_mode() -> str:
    return (getattr(settings, "MARKETPLACE_HTTP_MODE", "stub") or "stub").strip().lower()


class StubMarketplaceGateway:
    def __init__(self, *, provider: str, conn_settings: dict | None = None):
        self.provider = provider
        self.conn_settings = conn_settings or {}

    def fetch_orders(self, *, merchant_ref: str) -> list[dict[str, Any]]:
        # settings.stub_orders: lista canônica ou ifood-like injetada em lab
        orders = self.conn_settings.get("stub_orders") or []
        if not isinstance(orders, list):
            return []
        out = []
        for o in orders:
            if not isinstance(o, dict):
                continue
            row = dict(o)
            if merchant_ref and not row.get("merchant_ref"):
                row["merchant_ref"] = merchant_ref
            out.append(row)
        return out


class HttpMarketplaceGateway:
    """
    Cliente HTTP genérico.
    Endpoints configuráveis por connection.settings ou env global:

      orders_path: default /orders (GET, Authorization: Bearer)
      base_url: override por loja

    iFood/aiqfome reais expõem paths distintos — o path fica no merchant settings.
    """

    def __init__(
        self,
        *,
        provider: str,
        conn_settings: dict | None = None,
        session: requests.Session | None = None,
    ):
        self.provider = provider
        self.conn_settings = conn_settings or {}
        self.session = session or requests.Session()

    def _base_url(self) -> str:
        local = (self.conn_settings.get("base_url") or "").strip().rstrip("/")
        if local:
            return local
        if self.provider == "ifood":
            return (
                getattr(settings, "IFOOD_API_BASE_URL", "") or ""
            ).strip().rstrip("/")
        return (
            getattr(settings, "AIQFOME_API_BASE_URL", "") or ""
        ).strip().rstrip("/")

    def _token(self) -> str:
        return (
            self.conn_settings.get("access_token")
            or self.conn_settings.get("api_token")
            or (
                getattr(settings, "IFOOD_API_TOKEN", "")
                if self.provider == "ifood"
                else getattr(settings, "AIQFOME_API_TOKEN", "")
            )
            or ""
        ).strip()

    def fetch_orders(self, *, merchant_ref: str) -> list[dict[str, Any]]:
        base = self._base_url()
        token = self._token()
        if not base:
            raise MarketplaceConfigError(
                f"base_url ausente para marketplace {self.provider}."
            )
        if not token:
            raise MarketplaceConfigError(
                f"access_token ausente para marketplace {self.provider}."
            )
        path = (
            self.conn_settings.get("orders_path")
            or getattr(settings, "MARKETPLACE_ORDERS_PATH", "/orders")
            or "/orders"
        )
        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{base}{path}"
        params = {
            "merchant": merchant_ref,
            "merchantId": merchant_ref,
            "storeId": merchant_ref,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        extra = self.conn_settings.get("extra_headers") or {}
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items()})
        try:
            resp = self.session.get(
                url, headers=headers, params=params, timeout=_timeout()
            )
        except requests.RequestException as exc:
            raise MarketplaceHttpError(
                f"Falha HTTP marketplace {self.provider}: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise MarketplaceHttpError(
                f"Marketplace {self.provider} HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise MarketplaceHttpError("Resposta marketplace não-JSON.") from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("orders", "data", "items", "content", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []


def build_marketplace_gateway(
    *,
    provider: str,
    conn_settings: dict | None = None,
    session: requests.Session | None = None,
):
    provider = (provider or "").strip().lower()
    if provider not in {"ifood", "aiqfome"}:
        raise MarketplaceConfigError(f"Provider inválido: {provider}")
    mode = _http_mode()
    # Connection pode forçar stub incluso em modo http (lab)
    force = (conn_settings or {}).get("http_mode")
    if force in {"stub", "http"}:
        mode = force
    if mode == "http":
        return HttpMarketplaceGateway(
            provider=provider, conn_settings=conn_settings, session=session
        )
    return StubMarketplaceGateway(provider=provider, conn_settings=conn_settings)
