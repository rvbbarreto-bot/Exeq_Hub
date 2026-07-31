"""Adaptador SEFIN/ADN — emissor próprio Nacional (ADR-NFSE-001).

Stub (lab) por padrão; HTTP+mTLS com SEFIN_HTTP_MODE=http (M2+).
Código Focus permanece intocado (RF-50).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from integrations.nfse.port import NfseEmitResult
from integrations.nfse.sefin_client import SefinHttpClient, SefinHttpError
from integrations.nfse.sefin_codec import gzip_b64_to_xml

_FIXTURE_AUTHORIZED = (
    Path(__file__).resolve().parent / "tests" / "fixtures" / "nfse_autorizada_minimal.xml"
)

# Re-export para callers que importavam de sefin.py
__all__ = [
    "SefinHttpError",
    "SefinNfseProvider",
]


class SefinNfseProvider:
    """Implementa porta NfseProvider (RF-12)."""

    kind = "sefin"

    def __init__(
        self,
        *,
        environment: str | None = None,
        mode: str | None = None,
        tenant=None,
        cnpj: str = "",
        pfx_bytes: bytes | None = None,
        pfx_password: str = "",
        client: SefinHttpClient | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.environment = (
            environment
            or getattr(settings, "SEFIN_ENVIRONMENT", None)
            or "homolog"
        ).lower()
        self._mode = (mode or getattr(settings, "SEFIN_HTTP_MODE", None) or "stub").lower()
        self.tenant = tenant
        self.cnpj = "".join(ch for ch in (cnpj or "") if ch.isdigit())
        self._pfx_bytes = pfx_bytes
        self._pfx_password = pfx_password
        self._client = client
        self.timeout = timeout

    @property
    def mode(self) -> str:
        return self._mode

    def emitir(self, *, payload: dict[str, Any]) -> NfseEmitResult:
        if self.mode != "http":
            return self._stub_emit(payload)

        dps_xml = _resolve_dps_xml(payload)
        if not dps_xml:
            raise SefinHttpError(
                "Emissão SEFIN HTTP exige dps_xml (assinada) ou dps_xml_gzip_b64 no payload"
            )

        client = self._get_client()
        try:
            response = client.emitir_dps(dps_xml=dps_xml)
        finally:
            if self._client is None:
                client.close()

        return _map_emit_response(response.status_code, response.data, response.xml_bytes)

    def consultar(self, *, ref: str) -> NfseEmitResult:
        if self.mode != "http":
            return NfseEmitResult(
                external_ref=ref,
                status="authorized",
                raw={
                    "provider": "sefin",
                    "mode": "stub",
                    "action": "consultar",
                    "status": "authorized",
                    "xml": _stub_authorized_xml().decode("utf-8"),
                },
            )

        client = self._get_client()
        try:
            response = client.consultar_nfse(chave_acesso=ref)
        finally:
            if self._client is None:
                client.close()

        return _map_emit_response(response.status_code, response.data, response.xml_bytes, ref=ref)

    def cancelar(
        self,
        *,
        ref: str,
        justificativa: str,
        codigo_cancelamento: int | None = None,
        evento_xml: bytes | None = None,
    ) -> NfseEmitResult:
        if self.mode != "http":
            return NfseEmitResult(
                external_ref=ref,
                status="cancelled",
                raw={
                    "provider": "sefin",
                    "mode": "stub",
                    "action": "cancelar",
                    "status": "cancelled",
                    "justificativa": justificativa,
                    "codigo_cancelamento": codigo_cancelamento,
                },
            )
        if not evento_xml:
            raise SefinHttpError(
                "Cancelamento SEFIN HTTP exige evento_xml assinado (RF-31) — mapper de evento em M4"
            )
        client = self._get_client()
        try:
            response = client.registrar_evento(chave_acesso=ref, evento_xml=evento_xml)
        finally:
            if self._client is None:
                client.close()

        status = "cancelled" if response.status_code in {200, 201, 202} else "authorized"
        return NfseEmitResult(
            external_ref=ref,
            status=status,
            raw={
                "provider": "sefin",
                "mode": "http",
                "action": "cancelar",
                "http_status": response.status_code,
                "justificativa": justificativa,
                "codigo_cancelamento": codigo_cancelamento,
                **response.data,
            },
        )

    def _get_client(self) -> SefinHttpClient:
        if self._client is not None:
            return self._client
        pfx_bytes, password = self._load_pfx()
        return SefinHttpClient(
            pfx_bytes=pfx_bytes,
            pfx_password=password,
            environment=self.environment,
            timeout=self.timeout,
        )

    def _load_pfx(self) -> tuple[bytes, str]:
        if self._pfx_bytes is not None:
            return self._pfx_bytes, self._pfx_password
        if self.tenant is None or not self.cnpj:
            raise SefinHttpError(
                "SEFIN HTTP exige tenant + CNPJ do prestador para carregar certificado A1"
            )
        from apps.accounts.certificates import load_primary_pfx_material

        return load_primary_pfx_material(
            tenant=self.tenant,
            cnpj=self.cnpj,
            purpose="nfse",
        )

    def _stub_emit(self, payload: dict[str, Any]) -> NfseEmitResult:
        issue_id = str(payload.get("issue_id") or payload.get("ref") or "unknown")
        ref = f"SEFIN-{issue_id.replace('-', '')[:16].upper()}"
        xml = _stub_authorized_xml()
        return NfseEmitResult(
            external_ref=ref,
            status="authorized",
            raw={
                "provider": "sefin",
                "mode": "stub",
                "environment": self.environment,
                "status": "authorized",
                "xml": xml.decode("utf-8"),
                "danfse_layout_version": "nt008-v1.02",
            },
        )


def _resolve_dps_xml(payload: dict[str, Any]) -> bytes | None:
    raw = payload.get("dps_xml")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, str) and raw.strip().startswith("<"):
        return raw.encode("utf-8")
    b64 = payload.get("dps_xml_gzip_b64") or (payload.get("nfse") or {}).get("dpsXmlGZipB64")
    if b64:
        return gzip_b64_to_xml(b64)
    return None


def _map_emit_response(
    status_code: int,
    data: dict[str, Any],
    xml_bytes: bytes | None,
    *,
    ref: str = "",
) -> NfseEmitResult:
    chave = str(data.get("chaveAcesso") or data.get("chave_acesso") or ref or "")
    raw: dict[str, Any] = {
        "provider": "sefin",
        "mode": "http",
        "http_status": status_code,
        **data,
    }
    if xml_bytes:
        raw["xml"] = xml_bytes.decode("utf-8", errors="replace")

    if status_code in {200, 201} and (xml_bytes or chave):
        return NfseEmitResult(
            external_ref=chave or ref or "SEFIN-OK",
            status="authorized",
            raw=raw,
        )

    erros = data.get("erros") or data.get("errors") or data.get("mensagem")
    if status_code in {400, 422} or erros:
        raw["status"] = "rejected"
        return NfseEmitResult(
            external_ref=chave or ref or "SEFIN-REJECTED",
            status="rejected",
            raw=raw,
        )

    raw["status"] = "processing"
    return NfseEmitResult(
        external_ref=chave or ref or "SEFIN-PENDING",
        status="processing",
        raw=raw,
    )


def _stub_authorized_xml() -> bytes:
    if _FIXTURE_AUTHORIZED.is_file():
        return _FIXTURE_AUTHORIZED.read_bytes()
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<NFSe><infNFSe><nNFSe>0</nNFSe><cStat>100</cStat></infNFSe></NFSe>"
    )
