"""Formatação de exibição DANFSe (pt-BR) — não altera XML; só PDF."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def format_document(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) == 14:
        return (
            f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
            f"{digits[8:12]}-{digits[12:]}"
        )
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return value or "—"


def format_cep(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return value or ""


def format_money_br(value: str) -> str:
    raw = (value or "").strip()
    if not raw or raw in {"—", "-"}:
        return "—"
    try:
        amount = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return raw
    formatted = f"{amount:,.2f}"
    # 1,411.00 → 1.411,00
    formatted = formatted.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def format_percent_br(value: str) -> str:
    raw = (value or "").strip().rstrip("%")
    if not raw or raw in {"—", "-"}:
        return ""
    try:
        amount = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return f"{raw}%"
    formatted = f"{amount:.2f}".replace(".", ",")
    return f"{formatted}%"


def format_datetime_br(value: str) -> str:
    raw = (value or "").strip()
    if not raw or raw in {"—", "-"}:
        return "—"
    # 2026-07-30T19:35:25-03:00 | 2026-07-30T19:35:25 | 2026-07-30 19:35:25
    normalized = raw.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            # %z não aceita -03:00 com dois pontos em alguns Python — normaliza.
            candidate = normalized
            if fmt.endswith("%z") and re.search(r"[+-]\d{2}:\d{2}$", candidate):
                candidate = candidate[:-3] + candidate[-2:]
            dt = datetime.strptime(candidate, fmt)
            if fmt == "%Y-%m-%d":
                return dt.strftime("%d/%m/%Y")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            continue
    return raw


def format_competencia(value: str) -> str:
    """Competência NFS-e: preferir MM/AAAA."""
    raw = (value or "").strip()
    if not raw or raw in {"—", "-"}:
        return "—"
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 6:  # YYYYMM
        return f"{digits[4:6]}/{digits[:4]}"
    if len(digits) == 8:  # YYYYMMDD
        return f"{digits[4:6]}/{digits[:4]}"
    m = re.match(r"^(\d{4})-(\d{2})(?:-\d{2})?", raw)
    if m:
        return f"{m.group(2)}/{m.group(1)}"
    m2 = re.match(r"^(\d{2})/(\d{4})$", raw)
    if m2:
        return raw
    return raw


def format_endereco_display(value: str) -> str:
    """Aplica máscara de CEP em trechos de 8 dígitos no endereço montado."""
    if not value:
        return value

    def _cep(match: re.Match[str]) -> str:
        return format_cep(match.group(0))

    return re.sub(r"\b\d{8}\b", _cep, value)
