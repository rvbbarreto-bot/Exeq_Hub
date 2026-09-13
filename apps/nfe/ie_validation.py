"""Validação unificada de IE emitente — gate + tax + XML."""

from __future__ import annotations


def validate_emitter_ie(ie: str | None, *, http_mode: bool) -> tuple[bool, str]:
    ie = (ie or "").strip()
    digits = "".join(ch for ch in ie if ch.isdigit())
    isento = ie.upper() in {"ISENTO", "ISENTA"}
    if not http_mode:
        return True, f"IE={'ok' if ie else 'pendente (ok em stub)'}"
    if isento:
        return True, "IE isento"
    if len(digits) >= 2:
        return True, f"IE ok ({len(digits)} dig.)"
    return False, "IE pendente/inválida (obrigatória em http)"


def emitter_ie_error(ie: str | None, *, http_mode: bool) -> str | None:
    ok, _ = validate_emitter_ie(ie, http_mode=http_mode)
    if ok:
        return None
    return "IE do emitente obrigatória para HTTP SEFAZ"


def normalize_emitter_ie_for_xml(ie: str | None, *, tp_amb: str) -> str:
    raw = (ie or "").strip()
    if raw.upper() in {"ISENTO", "ISENTA"}:
        return "ISENTO"
    normalized = "".join(ch for ch in raw if ch.isalnum())
    if normalized:
        return normalized
    if tp_amb == "1":
        raise ValueError("IE do emitente obrigatória em produção (tpAmb=1)")
    return "ISENTO"
