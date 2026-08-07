"""RF-44 — grava tentativa SEFAZ redacted (emit/poll/evento)."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from integrations.sefaz_nfe.parse import sanitize_sefaz_raw


def record_transmission_attempt(
    *,
    tenant,
    invoice=None,
    stage: str,
    result=None,
    provider_kind: str = "",
    raw: dict | None = None,
    duration_ms: int | None = None,
    correlation_id: UUID | None = None,
):
    """
    Persist attempt. Fails soft (log) — never break fiscal path.
    `result` = NfeEmitResult-like (status, rejection_code, rejection_message, access_key, raw).
    """
    from apps.nfe.models import NfeTransmissionAttempt

    try:
        payload: dict[str, Any] = {}
        if raw and isinstance(raw, dict):
            payload = sanitize_sefaz_raw(raw)
        elif result is not None and isinstance(getattr(result, "raw", None), dict):
            payload = sanitize_sefaz_raw(result.raw)

        c_stat = ""
        x_motivo = ""
        http_status = None
        if result is not None:
            c_stat = str(getattr(result, "rejection_code", None) or payload.get("cStat") or "")
            x_motivo = str(
                getattr(result, "rejection_message", None) or payload.get("xMotivo") or ""
            )[:512]
            if payload.get("http") is not None:
                try:
                    http_status = int(payload["http"])
                except (TypeError, ValueError):
                    http_status = None
            result_status = str(getattr(result, "status", "") or "")
            access_key = str(getattr(result, "access_key", "") or "")[:44]
            corr = correlation_id or (
                getattr(invoice, "correlation_id", None) if invoice is not None else None
            )
        else:
            result_status = ""
            access_key = str(payload.get("chNFe") or "")[:44]
            c_stat = str(payload.get("cStat") or "")
            x_motivo = str(payload.get("xMotivo") or "")[:512]
            corr = correlation_id

        if invoice is not None and not access_key:
            access_key = (invoice.access_key or "")[:44]

        return NfeTransmissionAttempt.objects.create(
            tenant=tenant,
            invoice=invoice,
            stage=stage,
            provider_kind=(provider_kind or "")[:16],
            result_status=result_status[:32],
            http_status=http_status,
            c_stat=c_stat[:8],
            x_motivo=x_motivo,
            access_key=access_key,
            duration_ms=duration_ms,
            correlation_id=corr,
            raw=payload,
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception(
            "nfe.attempt_persist_failed stage=%s invoice=%s",
            stage,
            getattr(invoice, "id", None),
        )
        return None


class AttemptTimer:
    """Context manager que devolve duration_ms no __exit__ via .ms."""

    def __init__(self) -> None:
        self._t0 = 0.0
        self.ms: int | None = None

    def __enter__(self) -> AttemptTimer:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.ms = int((time.perf_counter() - self._t0) * 1000)
