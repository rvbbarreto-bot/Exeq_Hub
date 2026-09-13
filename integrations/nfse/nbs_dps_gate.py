"""Portão de transmissão do cNBS no XML DPS (evita E1235 até SEFIN aceitar no XSD)."""

from __future__ import annotations

from django.conf import settings

MODE_OFF = "off"
MODE_HOMOLOG = "homolog"
MODE_ON = "on"


def cnbs_dps_gate_mode() -> str:
    raw = getattr(settings, "NFSE_DPS_CNBS_MODE", MODE_OFF) or MODE_OFF
    mode = str(raw).strip().lower()
    if mode in {MODE_OFF, MODE_HOMOLOG, MODE_ON}:
        return mode
    return MODE_OFF


def include_cnbs_in_dps(*, tp_amb: int) -> bool:
    """
    Define se <cNBS> entra no DPS enviado à SEFIN.

    - off (default): nunca envia — produção segura enquanto XSD v1.01 rejeita cNBS em cServ.
    - homolog: só tpAmb=2 (homologação).
    - on: portão aberto (produção + homolog) — usar quando SEFIN autorizar o campo.
    """
    mode = cnbs_dps_gate_mode()
    if mode == MODE_ON:
        return True
    if mode == MODE_HOMOLOG:
        return int(tp_amb) == 2
    return False
