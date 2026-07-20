from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from integrations.nfse.port import NfseEmitResult
from integrations.nfse.router import LAYOUT_NFSEN, LAYOUT_NFSE

AUTHORIZED = frozenset(
    {
        "autorizado",
        "autorizado_aguardando_geracao_pdf",
        "authorized",
    }
)

CANCELLED = frozenset(
    {
        "cancelado",
        "cancelled",
        "nfe_cancelada",
    }
)


class FocusHttpError(RuntimeError):
    pass


class FocusNfseProvider:
    """Adaptador Focus NFe — layouts nfse (municipal) e nfsen (nacional)."""

    kind = "focus"

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        mode: str | None = None,
        layout: str = LAYOUT_NFSEN,
        timeout: float = 30.0,
    ):
        self.token = token if token is not None else (settings.FOCUS_API_TOKEN or "")
        self.base_url = (
            base_url
            or settings.FOCUS_API_BASE_URL
            or "https://homologacao.focusnfe.com.br"
        ).rstrip("/")
        self.mode = (mode or settings.FOCUS_HTTP_MODE or "stub").lower()
        self.layout = layout if layout in {LAYOUT_NFSE, LAYOUT_NFSEN} else LAYOUT_NFSEN
        self.timeout = timeout

    @property
    def _api_root(self) -> str:
        return "/v2/nfsen" if self.layout == LAYOUT_NFSEN else "/v2/nfse"

    def emitir(self, *, payload: dict[str, Any]) -> NfseEmitResult:
        if self.mode != "http":
            return self._stub_emit(payload)
        ref = str(payload.get("ref") or payload.get("issue_id") or "")
        body = payload.get("nfse") or payload.get("body") or {}
        response = self._request("POST", self._api_root, params={"ref": ref}, json=body)
        return self._to_result(ref=ref or str(response.get("ref", "")), data=response)

    def consultar(self, *, ref: str) -> NfseEmitResult:
        if self.mode != "http":
            return NfseEmitResult(
                external_ref=ref,
                status="authorized",
                raw={
                    "provider": "focus",
                    "mode": "stub",
                    "layout": self.layout,
                    "action": "consultar",
                },
            )
        response = self._request("GET", f"{self._api_root}/{ref}")
        return self._to_result(ref=ref, data=response)

    def cancelar(
        self,
        *,
        ref: str,
        justificativa: str,
        codigo_cancelamento: int | None = None,
    ) -> NfseEmitResult:
        if self.mode != "http":
            return NfseEmitResult(
                external_ref=ref,
                status="cancelled",
                raw={
                    "provider": "focus",
                    "mode": "stub",
                    "layout": self.layout,
                    "action": "cancelar",
                    "justificativa": justificativa,
                    "codigo_cancelamento": codigo_cancelamento,
                },
            )
        body: dict[str, Any] = {"justificativa": justificativa}
        if codigo_cancelamento is not None:
            body["codigo_cancelamento"] = codigo_cancelamento
        response = self._request("DELETE", f"{self._api_root}/{ref}", json=body)
        result = self._to_result(ref=ref, data=response, fallback_status="cancelled")
        status_raw = str(response.get("status") or "").lower()
        if status_raw in CANCELLED:
            return NfseEmitResult(
                external_ref=result.external_ref,
                status="cancelled",
                raw=result.raw,
            )
        return result

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.token:
            raise FocusHttpError("FOCUS_API_TOKEN não configurado")
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method,
                url,
                auth=(self.token, ""),
                headers={"Content-Type": "application/json"},
                **kwargs,
            )
        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text}
        if response.status_code >= 400:
            raise FocusHttpError(f"Focus HTTP {response.status_code}: {data}")
        return data if isinstance(data, dict) else {"data": data}

    def _to_result(
        self,
        *,
        ref: str,
        data: dict[str, Any],
        fallback_status: str = "processing",
    ) -> NfseEmitResult:
        status_raw = str(data.get("status") or fallback_status).lower()
        status = "authorized" if status_raw in AUTHORIZED else status_raw
        return NfseEmitResult(
            external_ref=str(data.get("ref") or ref),
            status=status,
            raw={"provider": "focus", "mode": "http", "layout": self.layout, **data},
        )

    def _stub_emit(self, payload: dict[str, Any]) -> NfseEmitResult:
        issue_id = str(payload.get("issue_id", "unknown"))
        prefix = "NFSEN" if self.layout == LAYOUT_NFSEN else "FOCUS"
        ref = f"{prefix}-{issue_id.replace('-', '')[:12].upper()}"
        return NfseEmitResult(
            external_ref=ref,
            status="authorized",
            raw={
                "provider": "focus",
                "mode": "stub",
                "layout": self.layout,
                "payload_keys": list(payload.keys()),
            },
        )
