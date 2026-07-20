"""OAuth client_credentials SERPRO SAPI (mTLS + Basic consumer)."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from integrations.receita.exceptions import ReceitaAuthError
from integrations.receita.mtls import MtlsMaterial, build_mtls_context


@dataclass
class SerproTokens:
    access_token: str
    jwt_token: str
    expires_at: float

    @property
    def valid(self) -> bool:
        return bool(self.access_token) and time.time() < (self.expires_at - 30)


class SerproAuthClient:
    def __init__(
        self,
        *,
        consumer_key: str,
        consumer_secret: str,
        pfx_bytes: bytes,
        pfx_password: str = "",
        auth_url: str | None = None,
        role_type: str | None = None,
        timeout: float = 30.0,
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.pfx_bytes = pfx_bytes
        self.pfx_password = pfx_password
        self.auth_url = (
            auth_url
            or getattr(settings, "SERPRO_AUTH_URL", None)
            or "https://autenticacao.sapi.serpro.gov.br/authenticate"
        )
        self.role_type = (
            role_type
            or getattr(settings, "SERPRO_ROLE_TYPE", None)
            or "TERCEIROS"
        )
        self.timeout = timeout
        self._tokens: SerproTokens | None = None
        self._mtls: MtlsMaterial | None = None

    def close(self) -> None:
        if self._mtls is not None:
            self._mtls.close()
            self._mtls = None

    def _ensure_mtls(self) -> MtlsMaterial:
        if self._mtls is None:
            self._mtls = build_mtls_context(
                pfx_bytes=self.pfx_bytes,
                password=self.pfx_password,
            )
        return self._mtls

    def get_tokens(self, *, force: bool = False) -> SerproTokens:
        if not force and self._tokens and self._tokens.valid:
            return self._tokens
        if not self.consumer_key or not self.consumer_secret:
            raise ReceitaAuthError("consumer_key/secret SERPRO ausentes")

        basic = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode()
        ).decode()
        mtls = self._ensure_mtls()
        try:
            with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                response = client.post(
                    self.auth_url,
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Role-Type": self.role_type,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                )
        except httpx.HTTPError as exc:
            raise ReceitaAuthError(f"Falha de rede na autenticação SERPRO: {exc}") from exc

        if response.status_code >= 400:
            raise ReceitaAuthError(
                f"Auth SERPRO HTTP {response.status_code}: {response.text[:500]}"
            )
        data: dict[str, Any] = response.json()
        access = str(data.get("access_token") or "")
        jwt = str(data.get("jwt_token") or data.get("jwt") or "")
        expires_in = int(data.get("expires_in") or 600)
        if not access:
            raise ReceitaAuthError(f"Auth SERPRO sem access_token: {data}")
        self._tokens = SerproTokens(
            access_token=access,
            jwt_token=jwt or access,
            expires_at=time.time() + expires_in,
        )
        return self._tokens
