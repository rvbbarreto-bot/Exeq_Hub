"""OAuth2 client_credentials + mTLS para Banco Inter (Cobrança BolePix)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from integrations.payments.errors import PaymentGatewayError
from integrations.payments.inter_mtls import InterMtlsMaterial, build_inter_mtls_context

DEFAULT_INTER_SCOPE = "boleto-cobranca.read boleto-cobranca.write"
TOKEN_SKEW_SECONDS = 60


@dataclass
class InterToken:
    access_token: str
    expires_at: float
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def valid(self) -> bool:
        return bool(self.access_token) and time.time() < (self.expires_at - TOKEN_SKEW_SECONDS)


@dataclass(frozen=True)
class InterCredentials:
    client_id: str
    client_secret: str
    cert_pem: str = ""
    key_pem: str = ""
    cert_path: str = ""
    key_path: str = ""
    scope: str = DEFAULT_INTER_SCOPE
    conta_corrente: str = ""

    @property
    def complete(self) -> bool:
        has_pem = bool(self.cert_pem.strip() and self.key_pem.strip())
        has_paths = bool(self.cert_path.strip() and self.key_path.strip())
        return bool(self.client_id.strip() and self.client_secret.strip() and (has_pem or has_paths))


class InterAuthClient:
    """Obtém e renova access_token; todas as chamadas usam mTLS."""

    def __init__(
        self,
        *,
        credentials: InterCredentials,
        base_url: str | None = None,
        token_path: str | None = None,
        timeout: float = 30.0,
    ):
        self.credentials = credentials
        self.base_url = (
            base_url
            or getattr(settings, "INTER_API_BASE_URL", "")
            or "https://cdpj-sandbox.partners.uatinter.co"
        ).rstrip("/")
        self.token_path = token_path or getattr(
            settings, "INTER_OAUTH_TOKEN_PATH", "/oauth/v2/token"
        )
        self.timeout = timeout
        self._token: InterToken | None = None
        self._mtls: InterMtlsMaterial | None = None

    def close(self) -> None:
        if self._mtls is not None:
            self._mtls.close()
            self._mtls = None

    def _ensure_mtls(self) -> InterMtlsMaterial:
        if self._mtls is None:
            creds = self.credentials
            self._mtls = build_inter_mtls_context(
                cert_pem=creds.cert_pem or None,
                key_pem=creds.key_pem or None,
                cert_path=creds.cert_path or None,
                key_path=creds.key_path or None,
            )
        return self._mtls

    def get_access_token(self, *, force: bool = False) -> str:
        if not force and self._token and self._token.valid:
            return self._token.access_token
        self._fetch_token()
        assert self._token is not None
        return self._token.access_token

    def _fetch_token(self) -> InterToken:
        creds = self.credentials
        if not creds.client_id or not creds.client_secret:
            raise PaymentGatewayError("INTER_CLIENT_ID/SECRET ausentes")

        mtls = self._ensure_mtls()
        url = f"{self.base_url}{self.token_path}"
        data = {
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "grant_type": "client_credentials",
            "scope": creds.scope or DEFAULT_INTER_SCOPE,
        }
        try:
            with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                response = client.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f"Falha de rede no OAuth Inter: {exc}") from exc

        try:
            payload = response.json()
        except Exception:
            payload = {"raw_text": response.text}

        if response.status_code >= 400:
            raise PaymentGatewayError(
                f"OAuth Inter HTTP {response.status_code}: {payload}"
            )
        if not isinstance(payload, dict):
            raise PaymentGatewayError(f"OAuth Inter resposta inválida: {payload}")

        access = str(payload.get("access_token") or "")
        if not access:
            raise PaymentGatewayError(f"OAuth Inter sem access_token: {payload}")

        expires_in = int(payload.get("expires_in") or 3600)
        self._token = InterToken(
            access_token=access,
            expires_at=time.time() + expires_in,
            token_type=str(payload.get("token_type") or "Bearer"),
            scope=str(payload.get("scope") or creds.scope),
        )
        return self._token

    def request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """HTTP autenticado (Bearer + mTLS). Retorna dict JSON."""
        token = self.get_access_token()
        mtls = self._ensure_mtls()
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        req_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **(headers or {}),
        }
        conta = (self.credentials.conta_corrente or "").strip()
        if conta and "x-conta-corrente" not in req_headers:
            req_headers["x-conta-corrente"] = conta

        try:
            with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                response = client.request(method, url, headers=req_headers, **kwargs)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f"Falha de rede Inter: {exc}") from exc

        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text} if response.text else {}

        if response.status_code >= 400:
            raise PaymentGatewayError(f"inter HTTP {response.status_code}: {data}")
        return data if isinstance(data, dict) else {"data": data}

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> bytes:
        """HTTP autenticado (Bearer + mTLS). Retorna corpo binário (ex.: PDF)."""
        token = self.get_access_token()
        mtls = self._ensure_mtls()
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        req_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/pdf",
            **(headers or {}),
        }
        conta = (self.credentials.conta_corrente or "").strip()
        if conta and "x-conta-corrente" not in {
            k.lower() for k in req_headers
        }:
            req_headers["x-conta-corrente"] = conta

        try:
            with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                response = client.request(method, url, headers=req_headers, **kwargs)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f"Falha de rede Inter: {exc}") from exc

        if response.status_code >= 400:
            raise PaymentGatewayError(
                f"inter HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.content


def resolve_inter_credentials(*, tenant=None) -> InterCredentials:
    """Monta credenciais a partir de TenantSecret e settings/env."""
    from apps.accounts.secrets import get_tenant_secret_plaintext

    def _secret(key: str) -> str:
        if tenant is None:
            return ""
        return get_tenant_secret_plaintext(
            tenant=tenant, provider="inter", key_name=key
        ) or ""

    allow_env = bool(
        getattr(settings, "ALLOW_ENV_INTER_CREDENTIALS_FALLBACK", True)
    )
    # Multi-tenant: com tenant explícito, não herdar INTER_* global (bleed).
    if tenant is not None and not allow_env:
        client_id = _secret("client_id")
        client_secret = _secret("client_secret")
        cert_pem = _secret("cert_pem")
        key_pem = _secret("key_pem")
        conta = _secret("conta_corrente")
        cert_path = ""
        key_path = ""
    else:
        client_id = _secret("client_id") or getattr(settings, "INTER_CLIENT_ID", "") or ""
        client_secret = (
            _secret("client_secret") or getattr(settings, "INTER_CLIENT_SECRET", "") or ""
        )
        cert_pem = _secret("cert_pem") or getattr(settings, "INTER_CERT_PEM", "") or ""
        key_pem = _secret("key_pem") or getattr(settings, "INTER_KEY_PEM", "") or ""
        cert_path = getattr(settings, "INTER_CERT_PATH", "") or ""
        key_path = getattr(settings, "INTER_KEY_PATH", "") or ""
        conta = (
            _secret("conta_corrente")
            or getattr(settings, "INTER_CONTA_CORRENTE", "")
            or ""
        )
    scope = getattr(settings, "INTER_OAUTH_SCOPE", "") or DEFAULT_INTER_SCOPE
    return InterCredentials(
        client_id=client_id.strip(),
        client_secret=client_secret.strip(),
        cert_pem=cert_pem.strip(),
        key_pem=key_pem.strip(),
        cert_path=cert_path.strip(),
        key_path=key_path.strip(),
        scope=scope.strip(),
        conta_corrente=conta.strip(),
    )


def build_inter_auth_client(*, tenant=None) -> InterAuthClient | None:
    """Retorna InterAuthClient se credenciais OAuth+mTLS estiverem completas."""
    creds = resolve_inter_credentials(tenant=tenant)
    if not creds.complete:
        return None
    return InterAuthClient(
        credentials=creds,
        base_url=getattr(settings, "INTER_API_BASE_URL", "") or "",
    )
