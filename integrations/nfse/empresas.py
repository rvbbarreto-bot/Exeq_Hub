from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from apps.master_data.models import Provider, TaxRegime
from integrations.nfse.focus import FocusHttpError


class FocusEmpresaClient:
    """CRUD enxuto de empresas Focus + hooks (mesmo token/Basic Auth)."""

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

    def upsert_empresa_from_provider(
        self,
        provider: Provider,
        *,
        enable_nfsen_homolog: bool = True,
        enable_nfsen_producao: bool = False,
    ) -> dict[str, Any]:
        body = self._provider_to_empresa_body(
            provider,
            enable_nfsen_homolog=enable_nfsen_homolog,
            enable_nfsen_producao=enable_nfsen_producao,
        )
        if self.mode != "http":
            return {
                "provider": "focus",
                "mode": "stub",
                "action": "upsert_empresa",
                "cnpj": provider.document,
                "body_keys": list(body.keys()),
            }
        try:
            return self._request("POST", "/v2/empresas", json=body)
        except FocusHttpError:
            # empresa já existente → atualiza
            return self._request("PUT", f"/v2/empresas/{provider.document}", json=body)

    def ensure_webhook(
        self,
        *,
        cnpj: str,
        url: str,
        event: str = "nfsen",
        authorization: str | None = None,
        authorization_header: str = "X-Focus-Authorization",
    ) -> dict[str, Any]:
        payload = {
            "cnpj": cnpj,
            "event": event,
            "url": url,
            "authorization": authorization,
            "authorization_header": authorization_header,
        }
        if self.mode != "http":
            return {
                "provider": "focus",
                "mode": "stub",
                "action": "ensure_webhook",
                **{k: v for k, v in payload.items() if k != "authorization"},
            }
        return self._request("POST", "/v2/hooks", json=payload)

    def _provider_to_empresa_body(
        self,
        provider: Provider,
        *,
        enable_nfsen_homolog: bool,
        enable_nfsen_producao: bool,
    ) -> dict[str, Any]:
        addr = provider.address or {}
        regime = {
            TaxRegime.SIMPLES: 1,
            TaxRegime.PRESUMIDO: 3,
            TaxRegime.REAL: 3,
        }.get(provider.tax_regime, 1)
        body: dict[str, Any] = {
            "nome": provider.legal_name,
            "nome_fantasia": provider.trade_name or provider.legal_name,
            "cnpj": provider.document,
            "regime_tributario": regime,
            "habilita_nfse": False,
            "habilita_nfsen_homologacao": enable_nfsen_homolog,
            "habilita_nfsen_producao": enable_nfsen_producao,
        }
        if provider.municipal_registration:
            try:
                body["inscricao_municipal"] = int(
                    "".join(ch for ch in provider.municipal_registration if ch.isdigit())
                )
            except ValueError:
                pass
        for src, dst in (
            ("logradouro", "logradouro"),
            ("bairro", "bairro"),
            ("uf", "uf"),
            ("municipio", "municipio"),
            ("complemento", "complemento"),
        ):
            if addr.get(src):
                body[dst] = addr[src]
        if addr.get("numero"):
            try:
                body["numero"] = int(str(addr["numero"]).split()[0])
            except ValueError:
                body["numero"] = str(addr["numero"])
        if addr.get("cep"):
            digits = "".join(ch for ch in str(addr["cep"]) if ch.isdigit())
            if digits:
                body["cep"] = int(digits)
        return body

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
