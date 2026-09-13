"""Mensagens amigáveis NFC-e (Hub / operação)."""

from __future__ import annotations

import json
from typing import Any

from integrations.sefaz_nfe.messages import format_sefaz_http_rejection

_CSC_MESSAGE = (
    "Não foi possível emitir a NFC-e: o Código de Segurança do Contribuinte (CSC) "
    "não está cadastrado para esta empresa. Entre em contato com o contador "
    "responsável para concluir a configuração."
)

_GATE_MESSAGES: dict[str, str] = {
    "csc": _CSC_MESSAGE,
    "cert": (
        "Certificado digital A1 ausente ou inválido para o emitente. "
        "Cadastre ou renove em Certificados ou fale com seu contador."
    ),
    "provider": "Nenhum emitente (CNPJ) ativo. Cadastre a empresa antes de emitir.",
    "series": (
        "Série de numeração NFC-e não configurada para este emitente. "
        "Solicite ao contador responsável a configuração da série."
    ),
    "uf": "UF do emitente incompleta. Atualize o cadastro da empresa.",
    "ibge_emit": "Código IBGE do município emitente ausente. Atualize o cadastro da empresa.",
    "address_min": "Endereço do emitente incompleto. Atualize o cadastro da empresa.",
    "crt": "Regime tributário (CRT) do emitente não informado.",
    "nfce_enabled": "Emissão NFC-e não está habilitada para este escritório.",
    "ie": (
        "Inscrição Estadual (IE) inválida para emissão em produção. "
        "Informe a IE numérica da empresa em Cadastro → Empresas "
        "(ISENTO só quando a SEFAZ reconhece o CNPJ como isento)."
    ),
}


_VALIDATION_FIELD_HINTS: dict[str, str] = {
    "provider.state_registration": (
        "Informe a Inscrição Estadual (IE) numérica da empresa em Cadastro → Empresas. "
        "Em produção a SEFAZ não aceita ISENTO se o CNPJ possui IE cadastrada."
    ),
}


def format_nfce_validation_errors(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return (
            "Emissão NFC-e indisponível no momento. "
            "Verifique a configuração fiscal ou fale com seu contador."
        )
    for err in errors:
        field = str(err.get("field") or "")
        if field in _VALIDATION_FIELD_HINTS:
            return _VALIDATION_FIELD_HINTS[field]
    first = str(errors[0].get("message") or "").strip()
    if first:
        return f"Não foi possível emitir a NFC-e: {first}"
    return (
        "Emissão NFC-e indisponível no momento. "
        "Verifique a configuração fiscal ou fale com seu contador."
    )


def format_nfce_gate_errors(failed: list[dict[str, Any]]) -> str:
    """Converte checks do gate em texto para operador (sem JSON técnico)."""
    if not failed:
        return format_nfce_validation_errors([])
    if failed and failed[0].get("field"):
        return format_nfce_validation_errors(failed)
    ids = [str(c.get("id") or "") for c in failed]
    if "csc" in ids:
        return _CSC_MESSAGE
    parts: list[str] = []
    for check in failed:
        cid = str(check.get("id") or "")
        if cid in _GATE_MESSAGES:
            parts.append(_GATE_MESSAGES[cid])
        elif check.get("label"):
            parts.append(str(check["label"]))
    if not parts:
        return format_nfce_validation_errors([])
    if len(parts) == 1:
        return parts[0]
    return "Emissão NFC-e indisponível: " + " ".join(parts[:2])


def format_nfce_rejection_message(
    rejection_code: str | None,
    rejection_message: str | None,
) -> str:
    """Texto amigável para detalhe/listagem (inclui registros legados técnicos)."""
    return format_sefaz_http_rejection(
        rejection_code,
        rejection_message,
        document_label="NFC-e",
    )


def format_nfce_emit_exception(exc: BaseException) -> str:
    """Erros do PDV/API — gate, validação JSON ou domínio."""
    from apps.nfce.exceptions import NfceGateError, NfceValidationError

    if isinstance(exc, NfceGateError):
        return str(exc)
    if isinstance(exc, NfceValidationError):
        try:
            parsed = json.loads(str(exc))
            if isinstance(parsed, list):
                return format_nfce_validation_errors(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        return str(exc) or format_nfce_validation_errors([])
    raw = str(exc or "").strip()
    if raw.startswith("[") and '"field"' in raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return format_nfce_validation_errors(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    if "HTTPSConnectionPool" in raw or "SSLCertVerificationError" in raw:
        from integrations.sefaz_nfe.messages import format_sefaz_transport_error

        return format_sefaz_transport_error(exc, document_label="NFC-e")
    return raw or format_nfce_validation_errors([])
