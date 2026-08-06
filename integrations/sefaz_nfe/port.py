"""Porta e adapters NF-e (stub / HTTP SEFAZ-SP) — ADR-NFE-001."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NfeEmitResult:
    status: str  # authorized | rejected | failed | polling | cancelled
    access_key: str = ""
    protocol: str = ""
    rejection_code: str = ""
    rejection_message: str = ""
    raw: dict[str, Any] | None = None


class NfeProvider(Protocol):
    kind: str

    def emitir(self, *, invoice_snapshot: dict[str, Any], context: dict[str, Any] | None = None) -> NfeEmitResult: ...

    def cancelar(
        self,
        *,
        access_key: str,
        justificativa: str,
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult: ...


class StubNfeProvider:
    kind = "stub"

    def emitir(
        self, *, invoice_snapshot: dict[str, Any], context: dict[str, Any] | None = None
    ) -> NfeEmitResult:
        from integrations.sefaz_nfe.access_key import build_access_key

        emit = invoice_snapshot.get("emitente") or {}
        header = invoice_snapshot.get("header") or {}
        uf = ((emit.get("address") or {}).get("uf") or "SP")
        try:
            key = build_access_key(
                uf=str(uf),
                issue_date_iso=str(header.get("issue_date") or "2026-01-01"),
                cnpj=str(emit.get("cnpj") or "00000000000000"),
                series=int(header.get("series") or 1),
                number=int(header.get("number") or 1),
            )
        except Exception:  # noqa: BLE001
            payload = repr(invoice_snapshot).encode("utf-8")
            digest = hashlib.sha256(payload).hexdigest()
            key = "".join(str(int(c, 16) % 10) for c in digest[:44]).ljust(44, "0")[:44]
        return NfeEmitResult(
            status="authorized",
            access_key=key,
            protocol=f"STUB{uuid4().hex[:12].upper()}",
            raw={"mode": "stub", "note": "sem SEFAZ"},
        )

    def cancelar(
        self,
        *,
        access_key: str,
        justificativa: str,
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult:
        return NfeEmitResult(
            status="cancelled",
            access_key=access_key,
            protocol=f"STUBCANC{uuid4().hex[:8].upper()}",
            raw={"mode": "stub", "justificativa": justificativa[:255]},
        )


class HttpNfeProvider:
    """SEFAZ-SP HTTP: monta XML, assina A1, envia NFeAutorizacao4."""

    kind = "sefaz"

    def _load_pfx(self, context: dict[str, Any] | None, cnpj: str) -> tuple[bytes, str]:
        ctx = context or {}
        tenant = ctx.get("tenant")
        if tenant is None:
            raise RuntimeError("context.tenant obrigatório em modo HTTP")
        from apps.accounts.certificates import load_primary_pfx_material

        return load_primary_pfx_material(tenant=tenant, cnpj=cnpj, purpose="nfe")

    def emitir(
        self, *, invoice_snapshot: dict[str, Any], context: dict[str, Any] | None = None
    ) -> NfeEmitResult:
        from integrations.sefaz_nfe.endpoints import resolve_endpoints
        from integrations.sefaz_nfe.sign import sign_nfe_xml, wrap_envi_nfe
        from integrations.sefaz_nfe.transport import post_nfe_autorizacao
        from integrations.sefaz_nfe.xml_nfe import access_key_from_signed_or_snap, build_nfe_xml

        emit = invoice_snapshot.get("emitente") or {}
        header = invoice_snapshot.get("header") or {}
        uf = ((emit.get("address") or {}).get("uf") or getattr(settings, "NFE_PIVOT_UF", "SP")).upper()
        tp_amb = str(header.get("tp_amb") or getattr(settings, "NFE_DEFAULT_TP_AMB", "2"))
        cnpj = "".join(ch for ch in str(emit.get("cnpj") or "") if ch.isdigit())

        dry = (getattr(settings, "NFE_HTTP_DRY_RUN", False) is True) or (
            str(getattr(settings, "NFE_HTTP_DRY_RUN", "")).lower() in ("1", "true", "yes")
        )

        try:
            pfx_bytes, password = self._load_pfx(context, cnpj)
        except Exception as exc:  # noqa: BLE001
            return NfeEmitResult(
                status="failed",
                rejection_code="CERT",
                rejection_message=f"Certificado A1 indisponível: {exc}",
                raw={"mode": "http", "stage": "cert"},
            )

        try:
            unsigned = build_nfe_xml(snapshot=invoice_snapshot)
            signed = sign_nfe_xml(nfe_xml=unsigned, pfx_bytes=pfx_bytes, password=password)
            access_key = access_key_from_signed_or_snap(signed, invoice_snapshot)
            lote = str(header.get("number") or 1).zfill(15)
            envi = wrap_envi_nfe(signed_nfe_xml=signed, id_lote=lote, ind_sinc="1")
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_http_build_sign_failed")
            return NfeEmitResult(
                status="failed",
                rejection_code="XML",
                rejection_message=f"Falha montagem/assinatura NF-e: {exc}",
                raw={"mode": "http", "stage": "sign"},
            )

        if dry:
            return NfeEmitResult(
                status="failed",
                rejection_code="DRY_RUN",
                rejection_message="NFE_HTTP_DRY_RUN: XML assinado ok, sem POST SEFAZ",
                access_key=access_key,
                raw={
                    "mode": "http",
                    "stage": "dry_run",
                    "xml_bytes": len(envi),
                    "access_key": access_key,
                },
            )

        try:
            eps = resolve_endpoints(uf=uf, tp_amb=tp_amb)
            resp = post_nfe_autorizacao(
                url=eps.autorizacao,
                envi_nfe_xml=envi,
                pfx_bytes=pfx_bytes,
                password=password,
                timeout=float(getattr(settings, "NFE_HTTP_TIMEOUT", 60) or 60),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_http_post_failed")
            return NfeEmitResult(
                status="failed",
                rejection_code="HTTP",
                rejection_message=f"Falha HTTP SEFAZ: {exc}",
                access_key=access_key,
                raw={"mode": "http", "stage": "transport"},
            )

        c_stat = resp.c_stat
        # 100 = autorizada; 104 lote processado (sinc pode embutir)
        if c_stat in ("100", "150"):
            return NfeEmitResult(
                status="authorized",
                access_key=resp.access_key or access_key,
                protocol=resp.protocol,
                raw={"mode": "http", "cStat": c_stat, "body": resp.body[:2000]},
            )
        if c_stat in ("103", "105"):
            return NfeEmitResult(
                status="polling",
                access_key=resp.access_key or access_key,
                protocol=resp.protocol,
                rejection_code=c_stat,
                rejection_message=resp.x_motivo or "lote em processamento",
                raw={"mode": "http", "cStat": c_stat, "body": resp.body[:2000]},
            )
        if c_stat:
            return NfeEmitResult(
                status="rejected",
                access_key=resp.access_key or access_key,
                rejection_code=c_stat,
                rejection_message=resp.x_motivo or "rejeição SEFAZ",
                raw={"mode": "http", "cStat": c_stat, "http": resp.http_status, "body": resp.body[:2000]},
            )
        return NfeEmitResult(
            status="failed",
            access_key=access_key,
            rejection_code=str(resp.http_status),
            rejection_message="Resposta SEFAZ sem cStat legível",
            raw={"mode": "http", "http": resp.http_status, "body": resp.body[:2000]},
        )

    def cancelar(
        self,
        *,
        access_key: str,
        justificativa: str,
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult:
        # Cancelamento completo (evento 110111) — onda U3.1; stub de erro claro.
        return NfeEmitResult(
            status="failed",
            access_key=access_key,
            rejection_code="CANCEL_PENDING",
            rejection_message=(
                "Cancelamento SEFAZ HTTP (evento 110111) ainda não liberado nesta onda; "
                "use modo stub ou aguarde U3.1. "
                f"Justificativa recebida ({len(justificativa)} chars)."
            ),
            raw={"mode": "http", "stage": "cancel_not_implemented"},
        )


def get_nfe_provider():
    mode = (getattr(settings, "NFE_HTTP_MODE", "stub") or "stub").lower()
    if mode == "http":
        return HttpNfeProvider()
    return StubNfeProvider()
