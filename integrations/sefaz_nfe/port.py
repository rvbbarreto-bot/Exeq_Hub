"""Porta e adapters NF-e (stub / HTTP SEFAZ-SP) — ADR-NFE-001 · I4 emit · I5 consultar."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from django.conf import settings

from integrations.sefaz_nfe.parse import map_cstat_to_status, sanitize_sefaz_raw

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NfeEmitResult:
    status: str  # authorized | rejected | failed | polling | cancelled
    access_key: str = ""
    protocol: str = ""
    rejection_code: str = ""
    rejection_message: str = ""
    raw: dict[str, Any] | None = None
    # I4: XML assinado para artefatos; NÃO copiar para event.metadata (usar sanitize)
    signed_xml: bytes | None = field(default=None, compare=False, hash=False, repr=False)


class NfeProvider(Protocol):
    kind: str

    def emitir(self, *, invoice_snapshot: dict[str, Any], context: dict[str, Any] | None = None) -> NfeEmitResult: ...

    def consultar(
        self,
        *,
        access_key: str = "",
        receipt: str = "",
        tp_amb: str = "2",
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult: ...

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
        from integrations.sefaz_nfe.xml_nfe import build_nfe_xml

        emit = invoice_snapshot.get("emitente") or {}
        header = invoice_snapshot.get("header") or {}
        uf = (emit.get("address") or {}).get("uf") or "SP"
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

        signed_xml = None
        try:
            signed_xml = build_nfe_xml(snapshot=invoice_snapshot, access_key=key)
        except Exception:  # noqa: BLE001
            signed_xml = None

        return NfeEmitResult(
            status="authorized",
            access_key=key,
            protocol=f"STUB{uuid4().hex[:12].upper()}",
            raw=sanitize_sefaz_raw({"mode": "stub", "note": "sem SEFAZ"}),
            signed_xml=signed_xml,
        )

    def consultar(
        self,
        *,
        access_key: str = "",
        receipt: str = "",
        tp_amb: str = "2",
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult:
        # Lab: consulta por chave/recibo reconcilia como autorizada (sem HTTP).
        key = "".join(ch for ch in str(access_key or "") if ch.isdigit())[:44]
        if not key and not receipt:
            return NfeEmitResult(
                status="failed",
                rejection_code="REF",
                rejection_message="consultar stub exige access_key ou receipt",
                raw=sanitize_sefaz_raw({"mode": "stub", "action": "consultar"}),
            )
        return NfeEmitResult(
            status="authorized",
            access_key=key,
            protocol=f"STUBPOLL{uuid4().hex[:8].upper()}",
            raw=sanitize_sefaz_raw(
                {
                    "mode": "stub",
                    "action": "consultar",
                    "nRec": receipt or "",
                    "chNFe": key,
                }
            ),
        )

    def cancelar(
        self,
        *,
        access_key: str,
        justificativa: str,
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult:
        signed_xml = None
        try:
            from integrations.sefaz_nfe.evento_cancel import build_cancel_from_context

            signed_xml = build_cancel_from_context(
                access_key=access_key,
                justificativa=justificativa,
                context=context,
            )
        except Exception:  # noqa: BLE001
            signed_xml = None
        return NfeEmitResult(
            status="cancelled",
            access_key=access_key,
            protocol=f"STUBCANC{uuid4().hex[:8].upper()}",
            raw=sanitize_sefaz_raw(
                {"mode": "stub", "justificativa_len": len(justificativa or "")}
            ),
            signed_xml=signed_xml,
        )


class HttpNfeProvider:
    """SEFAZ-SP HTTP: autorização (I4) + ret/consulta (I5)."""

    kind = "sefaz"

    def _load_pfx(self, context: dict[str, Any] | None, cnpj: str) -> tuple[bytes, str]:
        ctx = context or {}
        tenant = ctx.get("tenant")
        if tenant is None:
            raise RuntimeError("context.tenant obrigatório em modo HTTP")
        from apps.accounts.certificates import load_primary_pfx_material

        return load_primary_pfx_material(tenant=tenant, cnpj=cnpj, purpose="nfe")

    def _is_dry_run(self) -> bool:
        return (getattr(settings, "NFE_HTTP_DRY_RUN", False) is True) or (
            str(getattr(settings, "NFE_HTTP_DRY_RUN", "")).lower() in ("1", "true", "yes")
        )

    def _emitente_cnpj(self, context: dict[str, Any] | None, invoice_snapshot: dict | None = None) -> str:
        ctx = context or {}
        if ctx.get("cnpj"):
            return "".join(ch for ch in str(ctx["cnpj"]) if ch.isdigit())
        snap = invoice_snapshot or {}
        emit = snap.get("emitente") or {}
        return "".join(ch for ch in str(emit.get("cnpj") or "") if ch.isdigit())

    def _result_from_sefaz_resp(
        self,
        *,
        resp,
        stage: str,
        access_key_fallback: str = "",
        signed_xml: bytes | None = None,
    ) -> NfeEmitResult:
        status = map_cstat_to_status(resp.c_stat)
        raw = sanitize_sefaz_raw(
            {
                "mode": "http",
                "stage": stage,
                "http": resp.http_status,
                "cStat": resp.c_stat,
                "xMotivo": resp.x_motivo,
                "nProt": resp.protocol,
                "chNFe": resp.access_key or access_key_fallback,
                "lote_cStat": resp.lote_c_stat,
                "nRec": getattr(resp, "n_rec", "") or "",
                "body": resp.body,
            }
        )

        if not resp.c_stat and resp.http_status and resp.http_status >= 400:
            return NfeEmitResult(
                status="failed",
                access_key=access_key_fallback,
                rejection_code=str(resp.http_status),
                rejection_message="Resposta SEFAZ HTTP sem cStat legível",
                raw=raw,
                signed_xml=signed_xml,
            )

        key = resp.access_key or access_key_fallback
        if status == "authorized":
            return NfeEmitResult(
                status="authorized",
                access_key=key,
                protocol=resp.protocol,
                raw=raw,
                signed_xml=signed_xml,
            )
        if status == "polling":
            return NfeEmitResult(
                status="polling",
                access_key=key,
                protocol=resp.protocol,
                rejection_code=resp.c_stat,
                rejection_message=resp.x_motivo or "lote em processamento",
                raw=raw,
                signed_xml=signed_xml,
            )
        if status == "rejected":
            return NfeEmitResult(
                status="rejected",
                access_key=key,
                rejection_code=resp.c_stat,
                rejection_message=resp.x_motivo or "rejeição SEFAZ",
                raw=raw,
                signed_xml=signed_xml,
            )
        return NfeEmitResult(
            status="failed",
            access_key=key or access_key_fallback,
            rejection_code=resp.c_stat or str(resp.http_status),
            rejection_message=resp.x_motivo or "falha SEFAZ",
            raw=raw,
            signed_xml=signed_xml,
        )

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

        try:
            pfx_bytes, password = self._load_pfx(context, cnpj)
        except Exception as exc:  # noqa: BLE001
            return NfeEmitResult(
                status="failed",
                rejection_code="CERT",
                rejection_message=f"Certificado A1 indisponível: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cert"}),
            )

        signed: bytes | None = None
        access_key = ""
        try:
            unsigned = build_nfe_xml(snapshot=invoice_snapshot)
            signed = sign_nfe_xml(nfe_xml=unsigned, pfx_bytes=pfx_bytes, password=password)
            access_key = access_key_from_signed_or_snap(signed, invoice_snapshot)
            lote = str(header.get("number") or 1).zfill(15)[:15]
            envi = wrap_envi_nfe(signed_nfe_xml=signed, id_lote=lote, ind_sinc="1")
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_http_build_sign_failed")
            return NfeEmitResult(
                status="failed",
                rejection_code="XML",
                rejection_message=f"Falha montagem/assinatura NF-e: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "sign"}),
                signed_xml=None,
            )

        if self._is_dry_run():
            return NfeEmitResult(
                status="failed",
                rejection_code="DRY_RUN",
                rejection_message="NFE_HTTP_DRY_RUN: XML assinado ok, sem POST SEFAZ",
                access_key=access_key,
                raw=sanitize_sefaz_raw(
                    {
                        "mode": "http",
                        "stage": "dry_run",
                        "xml_bytes": len(envi),
                        "access_key": access_key,
                    }
                ),
                signed_xml=signed,
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
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "transport"}),
                signed_xml=signed,
            )

        return self._result_from_sefaz_resp(
            resp=resp,
            stage="autorizacao",
            access_key_fallback=access_key,
            signed_xml=signed,
        )

    def consultar(
        self,
        *,
        access_key: str = "",
        receipt: str = "",
        tp_amb: str = "2",
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult:
        from integrations.sefaz_nfe.endpoints import resolve_endpoints
        from integrations.sefaz_nfe.transport import (
            post_nfe_consulta_protocolo,
            post_nfe_ret_autorizacao,
        )

        key = "".join(ch for ch in str(access_key or "") if ch.isdigit())[:44]
        n_rec = "".join(ch for ch in str(receipt or "") if ch.isdigit())
        amb = str(tp_amb or getattr(settings, "NFE_DEFAULT_TP_AMB", "2")).strip()[:1] or "2"
        uf = str((context or {}).get("uf") or getattr(settings, "NFE_PIVOT_UF", "SP")).upper()
        cnpj = self._emitente_cnpj(context)

        if not n_rec and not key:
            return NfeEmitResult(
                status="failed",
                rejection_code="REF",
                rejection_message="consultar exige nRec (receipt) ou access_key",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "consulta_ref"}),
            )

        if self._is_dry_run():
            return NfeEmitResult(
                status="polling",
                access_key=key,
                rejection_code="DRY_RUN",
                rejection_message="NFE_HTTP_DRY_RUN: consulta sem POST SEFAZ",
                raw=sanitize_sefaz_raw(
                    {
                        "mode": "http",
                        "stage": "consulta_dry_run",
                        "nRec": n_rec,
                        "chNFe": key,
                    }
                ),
            )

        try:
            pfx_bytes, password = self._load_pfx(context, cnpj)
        except Exception as exc:  # noqa: BLE001
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="CERT",
                rejection_message=f"Certificado A1 indisponível: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cert"}),
            )

        try:
            eps = resolve_endpoints(uf=uf, tp_amb=amb)
            timeout = float(getattr(settings, "NFE_HTTP_TIMEOUT", 60) or 60)
            if n_rec:
                resp = post_nfe_ret_autorizacao(
                    url=eps.ret_autorizacao,
                    n_rec=n_rec,
                    tp_amb=amb,
                    pfx_bytes=pfx_bytes,
                    password=password,
                    timeout=timeout,
                )
                stage = "ret_autorizacao"
            else:
                resp = post_nfe_consulta_protocolo(
                    url=eps.consulta_protocolo,
                    access_key=key,
                    tp_amb=amb,
                    pfx_bytes=pfx_bytes,
                    password=password,
                    timeout=timeout,
                )
                stage = "consulta_protocolo"
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_http_consultar_failed")
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="HTTP",
                rejection_message=f"Falha HTTP SEFAZ consulta: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "consulta_transport"}),
            )

        return self._result_from_sefaz_resp(
            resp=resp,
            stage=stage,
            access_key_fallback=key,
        )

    def cancelar(
        self,
        *,
        access_key: str,
        justificativa: str,
        context: dict[str, Any] | None = None,
    ) -> NfeEmitResult:
        """Evento 110111 assinado + NFeRecepcaoEvento4 (I6)."""
        from integrations.sefaz_nfe.endpoints import resolve_endpoints
        from integrations.sefaz_nfe.evento_cancel import (
            NfeEventoBuildError,
            build_cancel_from_context,
        )
        from integrations.sefaz_nfe.sign import sign_evento_nfe_xml
        from integrations.sefaz_nfe.transport import post_nfe_evento

        ctx = context or {}
        key = "".join(ch for ch in str(access_key or "") if ch.isdigit())[:44]
        just = (justificativa or "").strip()
        if not (15 <= len(just) <= 255):
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="JUST",
                rejection_message="justificativa deve ter 15–255 caracteres",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cancel_just"}),
            )
        if not key or len(key) != 44:
            return NfeEmitResult(
                status="failed",
                rejection_code="CHAVE",
                rejection_message="chNFe inválida para cancelamento",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cancel_chave"}),
            )
        protocol = str(ctx.get("protocol") or "").strip()
        if not protocol:
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="NPROT",
                rejection_message="nProt da autorização ausente no cancelamento",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cancel_nprot"}),
            )

        cnpj = self._emitente_cnpj(ctx)
        if len(cnpj) != 14 and len(key) == 44:
            cnpj = key[6:20]
        amb = str(ctx.get("tp_amb") or getattr(settings, "NFE_DEFAULT_TP_AMB", "2")).strip()[:1] or "2"
        uf = str(ctx.get("uf") or getattr(settings, "NFE_PIVOT_UF", "SP")).upper()

        try:
            pfx_bytes, password = self._load_pfx(ctx, cnpj)
        except Exception as exc:  # noqa: BLE001
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="CERT",
                rejection_message=f"Certificado A1 indisponível: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cert"}),
            )

        signed: bytes | None = None
        try:
            unsigned = build_cancel_from_context(
                access_key=key,
                justificativa=just,
                context={
                    **ctx,
                    "cnpj": cnpj,
                    "protocol": protocol,
                    "tp_amb": amb,
                },
            )
            signed = sign_evento_nfe_xml(
                env_evento_xml=unsigned, pfx_bytes=pfx_bytes, password=password
            )
        except NfeEventoBuildError as exc:
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="XML",
                rejection_message=f"Evento cancel inválido: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cancel_build"}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_http_cancel_sign_failed")
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="XML",
                rejection_message=f"Falha montagem/assinatura evento 110111: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cancel_sign"}),
            )

        if self._is_dry_run():
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="DRY_RUN",
                rejection_message="NFE_HTTP_DRY_RUN: evento 110111 assinado, sem POST SEFAZ",
                raw=sanitize_sefaz_raw(
                    {
                        "mode": "http",
                        "stage": "cancel_dry_run",
                        "xml_bytes": len(signed or b""),
                        "chNFe": key,
                    }
                ),
                signed_xml=signed,
            )

        try:
            eps = resolve_endpoints(uf=uf, tp_amb=amb)
            resp = post_nfe_evento(
                url=eps.recepcao_evento,
                evento_xml=signed,
                pfx_bytes=pfx_bytes,
                password=password,
                timeout=float(getattr(settings, "NFE_HTTP_TIMEOUT", 60) or 60),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_http_cancel_post_failed")
            return NfeEmitResult(
                status="failed",
                access_key=key,
                rejection_code="HTTP",
                rejection_message=f"Falha HTTP SEFAZ cancel: {exc}",
                raw=sanitize_sefaz_raw({"mode": "http", "stage": "cancel_transport"}),
                signed_xml=signed,
            )

        status = map_cstat_to_status(resp.c_stat)
        raw = sanitize_sefaz_raw(
            {
                "mode": "http",
                "stage": "cancel_evento",
                "http": resp.http_status,
                "cStat": resp.c_stat,
                "xMotivo": resp.x_motivo,
                "nProt": resp.protocol,
                "chNFe": resp.access_key or key,
                "lote_cStat": resp.lote_c_stat,
                "tpEvento": "110111",
                "body": resp.body,
            }
        )

        if status == "cancelled":
            return NfeEmitResult(
                status="cancelled",
                access_key=resp.access_key or key,
                protocol=resp.protocol or protocol,
                raw=raw,
                signed_xml=signed,
            )
        if status == "rejected":
            return NfeEmitResult(
                status="rejected",
                access_key=key,
                rejection_code=resp.c_stat,
                rejection_message=resp.x_motivo or "rejeição no cancelamento",
                raw=raw,
                signed_xml=signed,
            )
        return NfeEmitResult(
            status="failed",
            access_key=key,
            rejection_code=resp.c_stat or str(resp.http_status),
            rejection_message=resp.x_motivo or "falha no cancelamento SEFAZ",
            raw=raw,
            signed_xml=signed,
        )


def get_nfe_provider():
    mode = (getattr(settings, "NFE_HTTP_MODE", "stub") or "stub").lower()
    if mode == "http":
        return HttpNfeProvider()
    return StubNfeProvider()
