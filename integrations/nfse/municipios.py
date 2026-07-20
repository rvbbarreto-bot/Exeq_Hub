from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

from integrations.nfse.focus import FocusHttpError

CACHE_TTL = int(getattr(settings, "FOCUS_MUNICIPIO_CACHE_TTL", 86400) or 86400)


class FocusMunicipioClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        mode: str | None = None,
        timeout: float = 30.0,
    ):
        self.token = token if token is not None else (settings.FOCUS_API_TOKEN or "")
        self.base_url = (
            base_url
            or settings.FOCUS_API_BASE_URL
            or "https://homologacao.focusnfe.com.br"
        ).rstrip("/")
        self.mode = (mode or settings.FOCUS_HTTP_MODE or "stub").lower()
        self.timeout = timeout

    def get_municipio(self, ibge_code: str) -> dict[str, Any]:
        key = f"focus:municipio:{ibge_code}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        if self.mode != "http":
            data = {
                "codigo_municipio": ibge_code,
                "nome_municipio": "Stub",
                "sigla_uf": "SP",
                "mode": "stub",
            }
            cache.set(key, data, CACHE_TTL)
            return data
        data = self._request("GET", f"/v2/municipios/{ibge_code}")
        cache.set(key, data, CACHE_TTL)
        return data

    def get_json_exemplo(self, ibge_code: str) -> dict[str, Any]:
        key = f"focus:municipio:json:{ibge_code}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        if self.mode != "http":
            data = {
                "codigo_municipio": ibge_code,
                "mode": "stub",
                "exemplo": {"layout": "nfsen"},
            }
            cache.set(key, data, CACHE_TTL)
            return data
        data = self._request("GET", f"/v2/municipios/{ibge_code}/json")
        cache.set(key, data, CACHE_TTL)
        return data

    def listar(self, **params) -> list | dict:
        if self.mode != "http":
            return [{"codigo_municipio": "3504107", "nome_municipio": "Atibaia", "mode": "stub"}]
        return self._request("GET", "/v2/municipios", params=params)

    def suggested_overrides(self, ibge_code: str) -> dict[str, Any]:
        """Extrai chaves úteis do JSON de exemplo para focus_field_overrides."""
        exemplo = self.get_json_exemplo(ibge_code)
        if not isinstance(exemplo, dict):
            return {}
        # Focus pode devolver o body direto ou aninhado
        body = exemplo.get("exemplo") or exemplo.get("nfse") or exemplo
        if not isinstance(body, dict):
            return {}
        keep = {
            k: body[k]
            for k in (
                "natureza_operacao",
                "regime_especial_tributacao",
                "codigo_tributacao_nacional_iss",
                "tributacao_iss",
                "item_lista_servico",
            )
            if k in body and body[k] not in (None, "")
        }
        return keep

    def _request(self, method: str, path: str, **kwargs) -> Any:
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
        return data
