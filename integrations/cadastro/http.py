from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from integrations.cadastro.exceptions import (
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)
from integrations.cadastro.mappers import map_brasilapi_cnpj
from integrations.cadastro.port import CadastralLookupResult


class CadastroHttpGateway:
    """Consulta CNPJ via provedor HTTP trocável (default: BrasilAPI)."""

    kind = "cadastro_http"

    def __init__(
        self,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        api_token: str | None = None,
    ):
        self.provider = (
            provider
            or getattr(settings, "CADASTRO_CNPJ_PROVIDER", None)
            or "brasilapi"
        ).lower()
        self.base_url = (
            base_url
            or getattr(settings, "CADASTRO_CNPJ_BASE_URL", None)
            or "https://brasilapi.com.br/api/cnpj/v1"
        ).rstrip("/")
        self.timeout = float(
            timeout
            if timeout is not None
            else getattr(settings, "CADASTRO_CNPJ_TIMEOUT", 3.0) or 3.0
        )
        self.api_token = api_token if api_token is not None else (
            getattr(settings, "CADASTRO_CNPJ_API_TOKEN", None) or ""
        )

    def lookup_cnpj(self, *, cnpj: str) -> CadastralLookupResult:
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        if self.provider in {"brasilapi", "brasil_api"}:
            return self._lookup_brasilapi(digits)
        # Hooks futuros: cnpja, serpro_cnpj — mesmo contrato.
        raise CadastroProviderUnavailableError(
            f"Provedor cadastral '{self.provider}' não implementado."
        )

    def _lookup_brasilapi(self, cnpj: str) -> CadastralLookupResult:
        url = f"{self.base_url}/{cnpj}"
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise CadastroProviderUnavailableError(
                "Consulta cadastral expirou (timeout). Preencha os dados manualmente."
            ) from exc
        except httpx.HTTPError as exc:
            raise CadastroProviderUnavailableError(
                "Provedor cadastral indisponível. Preencha os dados manualmente."
            ) from exc

        if response.status_code == 404:
            raise CadastroNotFoundError("CNPJ não encontrado na base cadastral.")
        if response.status_code >= 400:
            raise CadastroProviderUnavailableError(
                "Provedor cadastral retornou erro. Preencha os dados manualmente."
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise CadastroProviderUnavailableError(
                "Resposta inválida do provedor cadastral."
            ) from exc
        if not isinstance(payload, dict):
            raise CadastroProviderUnavailableError(
                "Resposta inválida do provedor cadastral."
            )
        result = map_brasilapi_cnpj(
            payload, cnpj=cnpj, provider_kind=f"{self.kind}:brasilapi"
        )
        payload_cnpj = "".join(
            ch for ch in str(payload.get("cnpj") or "") if ch.isdigit()
        )
        if payload_cnpj and payload_cnpj != cnpj:
            raise CadastroProviderUnavailableError(
                "Resposta cadastral não corresponde ao CNPJ consultado."
            )
        return result
