"""Adapter HTTP SERPRO Integra Contador (DAS via PGDASD/GERARDAS12)."""

from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from integrations.receita.auth import SerproAuthClient
from integrations.receita.exceptions import (
    ReceitaCredentialsMissingError,
    ReceitaHttpError,
    ReceitaHttpNotConfiguredError,
)
from integrations.receita.port import GuiaCapturaResult
from integrations.receita.serpro_payload import (
    build_gerar_das_envelope,
    map_gerar_das_response,
)


class ReceitaHttpGateway:
    """
    Canal único DAS: SERPRO Integra Contador.
    Requer consumer_key/secret + PFX A1 (mTLS) do contratante (CNPJ do prestador).
    """

    kind = "serpro"

    def __init__(
        self,
        *,
        consumer_key: str = "",
        consumer_secret: str = "",
        pfx_bytes: bytes = b"",
        pfx_password: str = "",
        contratante_cnpj: str = "",
        auth_url: str | None = None,
        gateway_url: str | None = None,
        timeout: float = 45.0,
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.pfx_bytes = pfx_bytes
        self.pfx_password = pfx_password
        self.contratante_cnpj = "".join(ch for ch in contratante_cnpj if ch.isdigit())
        self.gateway_url = (
            gateway_url
            or getattr(settings, "SERPRO_GATEWAY_URL", None)
            or "https://gateway.apiserpro.serpro.gov.br/integra-contador/v1"
        ).rstrip("/")
        self.timeout = timeout
        self._auth = SerproAuthClient(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            pfx_bytes=pfx_bytes,
            pfx_password=pfx_password,
            auth_url=auth_url,
            timeout=timeout,
        )

    def close(self) -> None:
        self._auth.close()

    def capturar_das(self, *, cnpj: str, competencia: str) -> GuiaCapturaResult:
        self._assert_ready()
        envelope = build_gerar_das_envelope(
            cnpj=cnpj or self.contratante_cnpj,
            competencia=competencia,
            id_sistema=getattr(settings, "SERPRO_ID_SISTEMA_DAS", "PGDASD") or "PGDASD",
            id_servico=getattr(settings, "SERPRO_ID_SERVICO_GERAR_DAS", "GERARDAS12")
            or "GERARDAS12",
            versao_sistema=getattr(settings, "SERPRO_VERSAO_SISTEMA", "1.0") or "1.0",
        )
        path = getattr(settings, "SERPRO_EMIT_PATH", "Emitir") or "Emitir"
        data = self._post_json(path, envelope)
        return map_gerar_das_response(data)

    def capturar_darf(self, *, cnpj: str, competencia: str) -> GuiaCapturaResult:
        servico = getattr(settings, "SERPRO_ID_SERVICO_GERAR_DARF", "") or ""
        if not servico:
            raise ReceitaHttpNotConfiguredError(
                "DARF via SERPRO ainda sem idServico configurado "
                "(SERPRO_ID_SERVICO_GERAR_DARF). Use tipo DAS ou configure o serviço."
            )
        self._assert_ready()
        envelope = build_gerar_das_envelope(
            cnpj=cnpj or self.contratante_cnpj,
            competencia=competencia,
            id_sistema=getattr(settings, "SERPRO_ID_SISTEMA_DARF", "PGDASD") or "PGDASD",
            id_servico=servico,
            versao_sistema=getattr(settings, "SERPRO_VERSAO_SISTEMA", "1.0") or "1.0",
        )
        path = getattr(settings, "SERPRO_EMIT_PATH", "Emitir") or "Emitir"
        data = self._post_json(path, envelope)
        result = map_gerar_das_response(data)
        raw = dict(result.raw or {})
        raw["idServico"] = servico
        raw["tipo"] = "DARF"
        return GuiaCapturaResult(
            valor_principal=result.valor_principal,
            valor_multa=result.valor_multa,
            valor_juros=result.valor_juros,
            linha_digitavel=result.linha_digitavel,
            pix_copia_cola=result.pix_copia_cola,
            compliance_status=result.compliance_status,
            compliance_motivo=result.compliance_motivo,
            data_vencimento=result.data_vencimento,
            pdf_bytes=result.pdf_bytes,
            raw=raw,
        )

    def _assert_ready(self) -> None:
        if not self.consumer_key or not self.consumer_secret:
            raise ReceitaCredentialsMissingError(
                "Credenciais SERPRO ausentes "
                "(TenantSecret provider=serpro consumer_key/secret ou env)."
            )
        if not self.pfx_bytes:
            raise ReceitaCredentialsMissingError(
                "PFX A1 ausente para mTLS SERPRO (certificado primary do CNPJ)."
            )

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        tokens = self._auth.get_tokens()
        url = f"{self.gateway_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "jwt_token": tokens.jwt_token,
            "Content-Type": "application/json",
        }
        mtls = self._auth._ensure_mtls()
        try:
            with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ReceitaHttpError(f"Falha de rede SERPRO {path}: {exc}") from exc

        if response.status_code == 401:
            tokens = self._auth.get_tokens(force=True)
            headers["Authorization"] = f"Bearer {tokens.access_token}"
            headers["jwt_token"] = tokens.jwt_token
            try:
                with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                    response = client.post(url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                raise ReceitaHttpError(f"Falha de rede SERPRO {path}: {exc}") from exc

        if response.status_code >= 400:
            raise ReceitaHttpError(
                f"SERPRO HTTP {response.status_code} em {path}: {response.text[:800]}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ReceitaHttpError(f"SERPRO retornou JSON inesperado em {path}")
        return data
