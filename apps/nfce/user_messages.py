"""Mensagens amigáveis NFC-e (Hub / operação)."""

from __future__ import annotations

from typing import Any

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
}


def format_nfce_gate_errors(failed: list[dict[str, Any]]) -> str:
    """Converte checks do gate em texto para operador (sem JSON técnico)."""
    if not failed:
        return (
            "Emissão NFC-e indisponível no momento. "
            "Verifique a configuração fiscal ou fale com seu contador."
        )
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
        return (
            "Emissão NFC-e indisponível no momento. "
            "Verifique a configuração fiscal ou fale com seu contador."
        )
    if len(parts) == 1:
        return parts[0]
    return "Emissão NFC-e indisponível: " + " ".join(parts[:2])
