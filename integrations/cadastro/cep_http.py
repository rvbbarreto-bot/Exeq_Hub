from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from integrations.cadastro.cep_port import CepLookupResult
from integrations.cadastro.exceptions import (
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)


class CepHttpGateway:
    """CEP via ViaCEP (IBGE nativo) — padrão de mercado para autofill de endereço."""

    kind = "cep_http"

    def __init__(self, *, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (
            base_url
            or getattr(settings, "CADASTRO_CEP_BASE_URL", None)
            or "https://viacep.com.br/ws"
        ).rstrip("/")
        self.timeout = float(
            timeout
            if timeout is not None
            else getattr(settings, "CADASTRO_CNPJ_TIMEOUT", 3.0) or 3.0
        )

    def lookup_cep(self, *, cep: str) -> CepLookupResult:
        digits = "".join(ch for ch in cep if ch.isdigit())[:8]
        if len(digits) != 8:
            raise CadastroNotFoundError("CEP inválido.")
        url = f"{self.base_url}/{digits}/json/"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
        except httpx.TimeoutException as exc:
            raise CadastroProviderUnavailableError(
                "Consulta de CEP expirou. Preencha o endereço manualmente."
            ) from exc
        except httpx.HTTPError as exc:
            raise CadastroProviderUnavailableError(
                "Consulta de CEP indisponível. Preencha o endereço manualmente."
            ) from exc

        if response.status_code == 404:
            raise CadastroNotFoundError("CEP não encontrado.")
        if response.status_code >= 400:
            raise CadastroProviderUnavailableError(
                "Consulta de CEP indisponível. Preencha o endereço manualmente."
            )
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise CadastroProviderUnavailableError(
                "Resposta inválida da consulta de CEP."
            ) from exc
        if not isinstance(payload, dict) or payload.get("erro"):
            raise CadastroNotFoundError("CEP não encontrado.")

        return CepLookupResult(
            cep=digits,
            logradouro=str(payload.get("logradouro") or "").strip(),
            bairro=str(payload.get("bairro") or "").strip(),
            municipio=str(payload.get("localidade") or "").strip(),
            uf=str(payload.get("uf") or "").strip().upper()[:2],
            codigo_municipio_ibge=str(payload.get("ibge") or "").strip(),
            raw=payload,
            provider_kind=f"{self.kind}:viacep",
        )
