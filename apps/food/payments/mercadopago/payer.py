"""Normalização de payer Food → Mercado Pago."""

from __future__ import annotations


def split_payer_name(name: str) -> tuple[str, str]:
    parts = (name or "").strip().split(None, 1)
    if not parts:
        return "Cliente", "Food"
    if len(parts) == 1:
        return parts[0][:255], "."
    return parts[0][:255], parts[1][:255]


def payer_document_type(digits: str) -> str:
    if len(digits) == 14:
        return "CNPJ"
    return "CPF"


def normalize_document(document: str) -> str:
    return "".join(ch for ch in (document or "") if ch.isdigit())
