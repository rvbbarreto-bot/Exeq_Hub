"""Formatação de exibição DANFE (pt-BR) — não altera valores fiscais."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def digits_only(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def danfe_upper(value: str) -> str:
    return (value or "").upper()


def format_nf_number(value: str) -> str:
    digits = digits_only(value)
    if not digits:
        return value or "—"
    try:
        n = int(digits)
    except ValueError:
        return value
    return f"{n:,}".replace(",", ".")


def format_phone_br(value: str) -> str:
    digits = digits_only(value)
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    return value or "—"


def format_approx_trib_percent(approx_value: str, total_nf_value: str) -> str:
    """Percentual Lei 12.741 — ex.: (16,2000%) sobre total da NF."""
    try:
        approx = Decimal((approx_value or "0").replace(",", "."))
        total = Decimal((total_nf_value or "0").replace(",", "."))
    except (InvalidOperation, ValueError):
        return ""
    if approx <= 0 or total <= 0:
        return ""
    pct = (approx / total) * Decimal(100)
    s = f"{pct:.4f}".rstrip("0").rstrip(".")
    if "." in s:
        whole, frac = s.split(".", 1)
        frac = frac.ljust(4, "0")[:4]
        s = f"{whole},{frac}"
    else:
        s = f"{s},0000"
    return f"({s}%)"


def format_weight_br(value: str) -> str:
    raw = (value or "").strip()
    if not raw or raw in {"—", "-"}:
        return "—"
    try:
        amount = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return raw
    formatted = f"{amount:,.3f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return formatted


def format_date_br(value: str) -> str:
    full = format_datetime_br(value)
    if full == "—":
        return full
    return full.split(" ")[0]


def format_time_br(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    full = format_datetime_br(raw)
    if " " in full:
        return full.split(" ", 1)[1]
    return "—"


def addresses_differ(a_key: str, b_key: str) -> bool:
    if not a_key or not b_key:
        return bool(b_key)
    return a_key != b_key


def format_access_key(key: str) -> str:
    k = digits_only(key)
    if len(k) != 44:
        return key or "—"
    return " ".join(k[i : i + 4] for i in range(0, 44, 4))


def is_valid_cnpj(value: str) -> bool:
    try:
        from shared.validators import validate_cnpj

        validate_cnpj(value)
        return True
    except (ValueError, ImportError):
        return False


def is_valid_cpf(value: str) -> bool:
    try:
        from shared.validators import validate_cpf

        validate_cpf(value)
        return True
    except (ValueError, ImportError):
        return False


def format_document(value: str, *, validate: bool = True) -> str:
    digits = digits_only(value)
    if len(digits) == 14:
        if validate and not is_valid_cnpj(digits):
            return digits
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    if len(digits) == 11:
        if validate and not is_valid_cpf(digits):
            return digits
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return value or "—"


def format_cep(value: str) -> str:
    digits = digits_only(value)
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
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return formatted


def format_qty(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    try:
        q = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return raw
    s = f"{q:.4f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def format_rate_br(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    try:
        rate = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return raw
    s = f"{rate:.2f}".rstrip("0").rstrip(".")
    return f"{s.replace('.', ',')}%"


def format_unit_price(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    try:
        q = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return raw
    # Preserve up to 10 decimal places from XML, trim trailing zeros.
    s = f"{q:.10f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def format_datetime_br(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    normalized = raw.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            from datetime import datetime

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


def wrap_text(text: str, *, max_chars: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
