"""Transmissão de eventos de manifestação do destinatário."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from integrations.sefaz_nfe.endpoints import resolve_endpoints
from integrations.sefaz_nfe.parse import parse_evento_response, sanitize_sefaz_raw
from integrations.sefaz_nfe.transport import post_nfe_evento

logger = logging.getLogger(__name__)

CSTAT_EVENTO_VINCULADO = "135"
CSTAT_LOTE_PROCESSADO = "128"


@dataclass(frozen=True)
class ManifestTransmitResult:
    c_stat: str
    x_motivo: str
    protocol: str
    access_key: str
    http_status: int = 200
    raw: dict[str, Any] | None = None


def _uf_from_access_key(access_key: str) -> str:
    from integrations.sefaz_nfe.access_key import UF_IBGE_CODE

    ch = "".join(c for c in access_key if c.isdigit())[:44]
    code = ch[:2] if len(ch) >= 2 else "35"
    for uf, ibge in UF_IBGE_CODE.items():
        if ibge == code:
            return uf
    return str(getattr(settings, "NFE_PIVOT_UF", "SP") or "SP")


def _stub_manifest_response(*, access_key: str, tp_evento: str) -> ManifestTransmitResult:
    return ManifestTransmitResult(
        c_stat=CSTAT_EVENTO_VINCULADO,
        x_motivo="Evento registrado e vinculado a NF-e (stub)",
        protocol="135260000888001",
        access_key=access_key,
        raw={"stub": True, "tpEvento": tp_evento},
    )


def transmit_manifestacao_evento(
    *,
    signed_env_evento_xml: bytes,
    access_key: str,
    tp_amb: str,
    tp_evento: str,
    pfx_bytes: bytes,
    password: str = "",
    http_session=None,
) -> ManifestTransmitResult:
    """POST NFeRecepcaoEvento4 ou stub lab."""
    key = "".join(c for c in access_key if c.isdigit())[:44]
    mode = (getattr(settings, "NFE_ENTRADA_HTTP_MODE", "stub") or "stub").lower()

    if mode == "stub" or getattr(settings, "NFE_ENTRADA_HTTP_DRY_RUN", False):
        return _stub_manifest_response(access_key=key, tp_evento=tp_evento)

    uf = _uf_from_access_key(key)
    eps = resolve_endpoints(uf=uf, tp_amb=str(tp_amb or "2"))
    timeout = float(getattr(settings, "NFE_ENTRADA_DIST_TIMEOUT", 60) or 60)

    resp = post_nfe_evento(
        url=eps.recepcao_evento,
        evento_xml=signed_env_evento_xml,
        pfx_bytes=pfx_bytes,
        password=password,
        timeout=timeout,
        session=http_session,
    )
    parsed = parse_evento_response(resp.body)
    return ManifestTransmitResult(
        c_stat=parsed.c_stat or resp.c_stat,
        x_motivo=parsed.x_motivo or resp.x_motivo,
        protocol=parsed.protocol or resp.protocol,
        access_key=parsed.access_key or key,
        http_status=resp.http_status,
        raw=sanitize_sefaz_raw(
            {
                "http_status": resp.http_status,
                "lote_c_stat": parsed.lote_c_stat,
                "tpEvento": tp_evento,
            }
        ),
    )


def is_manifest_accepted(c_stat: str) -> bool:
    code = str(c_stat or "").strip()
    return code in {CSTAT_EVENTO_VINCULADO, "136"}
