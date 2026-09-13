"""Horários fiscais SEFAZ — ISO com offset local e exibição DANFE."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

FISCAL_TZ = ZoneInfo("America/Sao_Paulo")


def fiscal_local_now() -> datetime:
    from django.utils import timezone

    return timezone.localtime(timezone.now(), FISCAL_TZ)


def format_fiscal_iso(dt: datetime | None = None) -> str:
    """Formato dhEmi/dhRecbto: 2026-09-05T23:19:45-03:00."""
    value = dt or fiscal_local_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=FISCAL_TZ)
    else:
        value = value.astimezone(FISCAL_TZ)
    offset = value.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return value.strftime(f"%Y-%m-%dT%H:%M:%S{offset}")


def parse_fiscal_datetime(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text[-6] in ("+", "-") and text[-3] == ":":
            return datetime.fromisoformat(text)
        if text[-5] in ("+", "-") and text[-3].isdigit():
            return datetime.fromisoformat(f"{text[:-2]}:{text[-2:]}")
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=FISCAL_TZ)
    except ValueError:
        return None


def format_fiscal_display(raw: str) -> str:
    """Converte para horário local (Manual DANFE NFC-e)."""
    dt = parse_fiscal_datetime(raw)
    if dt is None:
        text = (raw or "").strip()
        if len(text) >= 10 and text[4] == "-":
            return f"{text[8:10]}/{text[5:7]}/{text[:4]}"
        return text
    local = dt.astimezone(FISCAL_TZ)
    return local.strftime("%d/%m/%Y %H:%M")
