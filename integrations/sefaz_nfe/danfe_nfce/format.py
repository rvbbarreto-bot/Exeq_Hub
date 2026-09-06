"""Formatação pt-BR para DANFE NFC-e (Manual v6.0)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

TPAG_LABELS: dict[str, str] = {
    "01": "Dinheiro",
    "02": "Cheque",
    "03": "Cartão crédito",
    "04": "Cartão débito",
    "05": "Crédito loja",
    "10": "Vale alimentação",
    "11": "Vale refeição",
    "12": "Vale presente",
    "13": "Vale combustível",
    "15": "Boleto",
    "17": "Pix",
    "18": "Transferência",
    "99": "Outros",
}


def only_digits(value: str, *, max_len: int | None = None) -> str:
    out = "".join(ch for ch in str(value or "") if ch.isdigit())
    if max_len:
        return out[:max_len]
    return out


def format_br_money(raw: str | Decimal | float | int, *, decimals: int = 2) -> str:
    try:
        if isinstance(raw, int):
            amount = Decimal(raw) / Decimal(100)
        else:
            amount = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    quant = Decimal("1").scaleb(-decimals)
    text = str(amount.quantize(quant))
    if "." in text:
        whole, frac = text.split(".", 1)
    else:
        whole, frac = text, "0" * decimals
    whole = f"{int(whole):,}".replace(",", ".")
    return f"{whole},{frac[:decimals].ljust(decimals, '0')}"


def format_br_qty(raw: str) -> str:
    try:
        qty = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        return raw or "1"
    text = f"{qty:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def mask_cnpj(value: str) -> str:
    d = only_digits(value, max_len=14).zfill(14)[-14:]
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def mask_cpf(value: str) -> str:
    d = only_digits(value, max_len=11).zfill(11)[-11:]
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def format_emit_address(parts: dict[str, str]) -> str:
    street = parts.get("street") or ""
    number = parts.get("number") or ""
    district = parts.get("district") or ""
    city = parts.get("city") or ""
    uf = parts.get("uf") or ""
    head = ", ".join(p for p in (street, number) if p)
    tail = " - ".join(p for p in (district, f"{city}/{uf}" if city or uf else "") if p)
    if head and tail:
        return f"{head} - {tail}"
    return head or tail


def parse_address_line(line: str) -> dict[str, str]:
    """Best-effort a partir do endereço concatenado do XML."""
    text = (line or "").strip()
    if not text:
        return {}
    parts = text.split()
    uf = parts[-2] if len(parts) >= 2 and len(parts[-2]) == 2 else ""
    city = parts[-3] if len(parts) >= 3 else ""
    return {
        "street": text[:40],
        "number": "",
        "district": "",
        "city": city,
        "uf": uf,
    }


def format_dh_emi(raw: str) -> str:
    from integrations.sefaz_nfe.fiscal_time import format_fiscal_display

    return format_fiscal_display(raw)


def format_nfce_number(raw: str) -> str:
    digits = only_digits(raw)
    return digits.zfill(9) if digits else "—"


def format_series(raw: str) -> str:
    digits = only_digits(raw)
    return digits.zfill(3) if digits else "—"


def tpag_label(code: str) -> str:
    code = (code or "99").strip().zfill(2)[-2:]
    return TPAG_LABELS.get(code, f"tPag {code}")


def sum_item_quantities(items: list[dict[str, str]]) -> str:
    """Soma qCom de todas as linhas (unidades compradas no cupom)."""
    from decimal import Decimal, InvalidOperation

    total = Decimal("0")
    for it in items:
        raw = (it.get("qty") or "0").strip().replace(",", ".")
        try:
            total += Decimal(raw)
        except InvalidOperation:
            continue
    if total == total.to_integral_value():
        return str(int(total))
    return format_br_qty(str(total))


def wrap_center(text: str, *, width: int = 46) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def pct_from_values(value: str, base: str) -> str:
    try:
        v = Decimal(str(value).replace(",", "."))
        b = Decimal(str(base).replace(",", "."))
        if b <= 0:
            return "0,00"
        return format_br_money(v / b * 100, decimals=2)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return "0,00"
