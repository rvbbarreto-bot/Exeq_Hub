"""Cliente HTTP mTLS SEFIN Nacional (ADR-NFSE-001 / LLR RF-12/13)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from integrations.nfse.sefin_codec import gzip_b64_to_xml, xml_to_gzip_b64
from integrations.nfse.sefin_mtls import SefinMtlsError, SefinMtlsMaterial, build_sefin_mtls_context

logger = logging.getLogger(__name__)

SEFIN_BASE_HOMOLOG = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
SEFIN_BASE_PROD = "https://sefin.nfse.gov.br/SefinNacional"


class SefinHttpError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, raw: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw or {}


@dataclass(frozen=True)
class SefinHttpResponse:
    status_code: int
    data: dict[str, Any]
    xml_bytes: bytes | None = None


def resolve_sefin_base_url(*, environment: str = "homolog") -> str:
    override = (getattr(settings, "SEFIN_BASE_URL", None) or "").strip()
    if override:
        return override.rstrip("/")
    env = (environment or "homolog").lower()
    if env in {"prod", "production", "producao", "produção"}:
        return (
            getattr(settings, "SEFIN_BASE_URL_PROD", None) or SEFIN_BASE_PROD
        ).rstrip("/")
    return (
        getattr(settings, "SEFIN_BASE_URL_HOMOLOG", None) or SEFIN_BASE_HOMOLOG
    ).rstrip("/")


class SefinHttpClient:
    """POST/GET SEFIN com mTLS. Sem OAuth/API key (D-08 / LLR §1.3)."""

    def __init__(
        self,
        *,
        pfx_bytes: bytes,
        pfx_password: str = "",
        environment: str = "homolog",
        base_url: str | None = None,
        timeout: float | None = None,
        max_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        self.environment = environment
        self.base_url = (base_url or resolve_sefin_base_url(environment=environment)).rstrip(
            "/"
        )
        self.timeout = float(
            timeout
            if timeout is not None
            else getattr(settings, "SEFIN_HTTP_TIMEOUT_SECONDS", 45.0)
        )
        self.max_attempts = max(
            1,
            int(
                max_attempts
                if max_attempts is not None
                else getattr(settings, "SEFIN_HTTP_MAX_ATTEMPTS", 3)
            ),
        )
        self.retry_backoff_seconds = float(
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else getattr(settings, "SEFIN_HTTP_RETRY_BACKOFF_SECONDS", 0.5)
        )
        self._pfx_bytes = pfx_bytes
        self._pfx_password = pfx_password
        self._mtls: SefinMtlsMaterial | None = None

    def close(self) -> None:
        if self._mtls is not None:
            self._mtls.close()
            self._mtls = None

    def _ensure_mtls(self) -> SefinMtlsMaterial:
        if self._mtls is None:
            self._mtls = build_sefin_mtls_context(
                pfx_bytes=self._pfx_bytes,
                password=self._pfx_password,
            )
        return self._mtls

    def handshake(self) -> dict[str, Any]:
        """Prova mTLS: abre TLS e faz HEAD/GET leve na raiz da API."""
        mtls = self._ensure_mtls()
        url = f"{self.base_url}/nfse"
        try:
            with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                # GET sem chave tende a 404/405 — prova que o handshake passou.
                response = client.request("GET", url)
        except httpx.HTTPError as exc:
            raise SefinHttpError(f"Falha de transporte/mTLS SEFIN: {exc}") from exc
        except SefinMtlsError:
            raise
        evidence = {
            "provider": "sefin",
            "action": "handshake",
            "base_url": self.base_url,
            "http_status": response.status_code,
            "mtls": True,
        }
        logger.info(
            "SEFIN mTLS handshake status=%s host=%s",
            response.status_code,
            self.base_url,
        )
        return evidence

    def emitir_dps(self, *, dps_xml: bytes) -> SefinHttpResponse:
        body = {"dpsXmlGZipB64": xml_to_gzip_b64(dps_xml)}
        return self._request_json("POST", "/nfse", json_body=body)

    def consultar_nfse(self, *, chave_acesso: str) -> SefinHttpResponse:
        chave = "".join(ch for ch in chave_acesso if ch.isalnum())
        return self._request_json("GET", f"/nfse/{chave}")

    def consultar_dps(self, *, id_dps: str) -> SefinHttpResponse:
        return self._request_json("GET", f"/dps/{id_dps}")

    def registrar_evento(self, *, chave_acesso: str, evento_xml: bytes) -> SefinHttpResponse:
        chave = "".join(ch for ch in chave_acesso if ch.isalnum())
        body = {"pedidoRegistroEventoXmlGZipB64": xml_to_gzip_b64(evento_xml)}
        return self._request_json("POST", f"/nfse/{chave}/eventos", json_body=body)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> SefinHttpResponse:
        """HTTP com retry só em transporte/5xx; 4xx nunca repete (SEC-P1-07)."""
        mtls = self._ensure_mtls()
        url = f"{self.base_url}{path}"
        response: httpx.Response | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout, verify=mtls.ssl_context) as client:
                    response = client.request(
                        method,
                        url,
                        json=json_body,
                        headers={"Accept": "application/json"},
                    )
            except httpx.HTTPError as exc:
                if attempt >= self.max_attempts:
                    raise SefinHttpError(f"Falha HTTP SEFIN: {exc}") from exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code >= 500:
                if attempt >= self.max_attempts:
                    data = _safe_json(response)
                    sanitized = _sanitize_raw(data)
                    raise SefinHttpError(
                        f"SEFIN HTTP {response.status_code}",
                        status_code=response.status_code,
                        raw=sanitized,
                    )
                logger.warning(
                    "SEFIN HTTP %s tentativa %s/%s path=%s",
                    response.status_code,
                    attempt,
                    self.max_attempts,
                    path,
                )
                self._sleep_backoff(attempt)
                continue

            # 2xx / 4xx — sem retry (rejeição fiscal não martela).
            break

        if response is None:
            raise SefinHttpError("Falha HTTP SEFIN: sem resposta")

        data = _safe_json(response)
        xml_bytes = _extract_xml(data)
        sanitized = _sanitize_raw(data)
        return SefinHttpResponse(
            status_code=response.status_code,
            data=sanitized,
            xml_bytes=xml_bytes,
        )

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * attempt
        if delay > 0:
            time.sleep(delay)


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        text = (response.text or "")[:500]
        return {"http_status": response.status_code, "body_text": text}
    if isinstance(payload, dict):
        return payload
    return {"http_status": response.status_code, "body": payload}


def _extract_xml(data: dict[str, Any]) -> bytes | None:
    for key in ("nfseXmlGZipB64", "xmlGZipB64", "dpsXmlGZipB64"):
        value = data.get(key)
        if value:
            try:
                return gzip_b64_to_xml(value)
            except Exception:  # noqa: BLE001
                continue
    inline = data.get("xml") or data.get("nfseXml")
    if isinstance(inline, str) and "<" in inline:
        return inline.encode("utf-8")
    return None


def _sanitize_raw(data: dict[str, Any]) -> dict[str, Any]:
    """Remove envelopes enormes do raw persistido; mantém metadados úteis."""
    out = dict(data)
    for key in ("nfseXmlGZipB64", "dpsXmlGZipB64", "pedidoRegistroEventoXmlGZipB64", "xmlGZipB64"):
        if key in out and out[key]:
            out[key] = f"<omitted len={len(str(out[key]))}>"
    return out
