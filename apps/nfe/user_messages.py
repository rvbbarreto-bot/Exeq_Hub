"""Mensagens amigáveis NF-e (Hub / operação)."""

from __future__ import annotations

import json
from typing import Any

from apps.nfe.exceptions import NfeValidationError

_CUSTOMER_ADDRESS_FIELDS = frozenset(
    {
        "customer.address",
        "customer.address.uf",
        "customer.address.codigo_ibge",
    }
)

_PROVIDER_ADDRESS_FIELDS = frozenset(
    {
        "provider.address",
        "provider.address.uf",
        "provider.address.codigo_ibge",
    }
)

_FIELD_LABELS: dict[str, str] = {
    "customer.address.uf": "UF do destinatário",
    "customer.address.codigo_ibge": "código IBGE do município do destinatário",
    "customer.address": "endereço completo do destinatário",
    "customer.ie": "inscrição estadual do destinatário",
    "customer": "documento do destinatário",
    "provider.address.uf": "UF do emitente",
    "provider.address.codigo_ibge": "código IBGE do município do emitente",
    "provider.address": "endereço do emitente",
    "provider.tax_regime": "regime tributário (CRT) do emitente",
    "provider.state_registration": "inscrição estadual do emitente",
    "items": "itens da nota",
}


def _error_fields(errors: list[dict[str, Any]]) -> set[str]:
    return {str(e.get("field") or "") for e in errors}


def format_nfe_field_errors(errors: list[dict[str, Any]]) -> str:
    """Texto único para operador — sem JSON técnico."""
    if not errors:
        return (
            "Não foi possível emitir a NF-e. Verifique os dados ou fale com "
            "o contador responsável."
        )

    fields = _error_fields(errors)
    customer_addr = bool(fields & _CUSTOMER_ADDRESS_FIELDS)
    provider_addr = bool(fields & _PROVIDER_ADDRESS_FIELDS)

    if customer_addr and not provider_addr:
        return (
            "Não foi possível emitir a NF-e: o destinatário selecionado está com "
            "cadastro incompleto (faltam UF e/ou município com código IBGE de "
            "7 dígitos). Atualize o cliente em Cadastro → Clientes ou solicite "
            "ao contador responsável que conclua o endereço fiscal."
        )
    if provider_addr and not customer_addr:
        return (
            "Não foi possível emitir a NF-e: a empresa emitente está com cadastro "
            "incompleto (UF, município/IBGE ou endereço). Revise em Cadastro → "
            "Empresas ou fale com o contador responsável."
        )
    if customer_addr and provider_addr:
        return (
            "Não foi possível emitir a NF-e: emitente e destinatário possuem "
            "cadastros incompletos (UF e código IBGE obrigatórios). Atualize "
            "empresa e cliente ou solicite apoio ao contador responsável."
        )

    parts: list[str] = []
    for err in errors[:4]:
        field = str(err.get("field") or "")
        parts.append(_FIELD_LABELS.get(field) or str(err.get("message") or field))
    detail = "; ".join(p for p in parts if p)
    return f"Não foi possível emitir a NF-e: {detail}."


def parse_nfe_validation_error(
    exc: NfeValidationError | str,
) -> tuple[str, list[dict[str, Any]], dict[str, str] | None]:
    """
    Retorna (mensagem, field_errors, ação sugerida na UI).
    ação: {"label": "...", "url_name": "...", "url_args": [...]}
    """
    raw = str(exc)
    try:
        parsed = json.loads(raw)
        errors = parsed if isinstance(parsed, list) else [{"message": raw}]
    except json.JSONDecodeError:
        return raw, [], None

    message = format_nfe_field_errors(errors)
    fields = _error_fields(errors)
    action: dict[str, str] | None = None
    if fields & _CUSTOMER_ADDRESS_FIELDS or any(f.startswith("customer.") for f in fields):
        action = {
            "label": "Editar destinatário",
            "hint": "customer",
        }
    elif fields & _PROVIDER_ADDRESS_FIELDS or any(f.startswith("provider.") for f in fields):
        action = {
            "label": "Editar empresa emitente",
            "hint": "provider",
        }
    return message, errors, action
