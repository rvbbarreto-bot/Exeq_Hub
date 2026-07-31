"""Pilar 4 — consolidação forense do snapshot fiscal da emissão."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_forensic_snapshot(
    *,
    iss_payload: dict,
    rtc_block: dict | None,
    national_catalog: dict | None,
    internal_payload: dict | None = None,
    focus_ref: str = "",
    layout: str = "",
) -> dict[str, Any]:
    """
    Pacote imutável para defesa perante Fisco/contador.
    Não substitui artefato XML; complementa regra + RTC + hashes.
    """
    body = {
        "schema": "exeq.fiscal.forensic.v1",
        "layout": layout,
        "focus_ref": focus_ref or "",
        "iss": iss_payload,
        "rtc": rtc_block or {"status": "absent"},
        "national_catalog": national_catalog or {"status": "absent"},
    }
    if internal_payload is not None:
        raw = json.dumps(internal_payload, sort_keys=True, default=str).encode("utf-8")
        body["internal_payload_sha256"] = hashlib.sha256(raw).hexdigest()
    forensic_raw = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    body["forensic_sha256"] = hashlib.sha256(forensic_raw).hexdigest()
    return body


def merge_snapshot(iss_payload: dict, forensic: dict) -> dict:
    out = dict(iss_payload)
    out["forensic"] = forensic
    if forensic.get("rtc"):
        out["rtc"] = forensic["rtc"]
    if forensic.get("national_catalog"):
        out["national_catalog"] = forensic["national_catalog"]
    return out
