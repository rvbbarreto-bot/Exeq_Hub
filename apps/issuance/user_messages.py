"""Mensagens amigáveis para emissão NFS-e (Hub / operação)."""

from __future__ import annotations

from typing import Any

from apps.issuance.models import NfIssue, NfIssueEvent

_STATUS_LABELS: dict[str, str] = {
    "draft": "Rascunho",
    "pending_tax": "Tributação",
    "queued": "Na fila",
    "submitting": "Enviando",
    "polling": "Processando",
    "authorized": "Autorizada",
    "rejected": "Rejeitada",
    "cancelled": "Cancelada",
    "failed": "Falhou",
}

_ACTOR_LABELS: dict[str, str] = {
    "api": "Emissão via sistema",
    "worker": "Processamento automático",
    "provider": "SEFIN Nacional",
    "system": "Sistema",
    "hub": "Usuário no Hub",
    "webhook": "Retorno automático",
    "portal_sync": "Consulta ao portal",
    "admin": "Administrador",
}

_INTERNAL_REJECTIONS: dict[str, dict[str, str]] = {
    "CERT_NOT_USABLE": {
        "title": "Certificado digital indisponível",
        "message": (
            "O certificado A1 do CNPJ emitente não está cadastrado, expirou "
            "ou não pode ser usado para assinar a NFS-e."
        ),
        "hint": "Cadastre ou renove o certificado em Certificados, vinculado ao mesmo CNPJ da emissão.",
    },
    "TAX_RULE_NOT_FOUND": {
        "title": "Regra fiscal não configurada",
        "message": (
            "Não há regra ISS para a combinação serviço, município (IBGE) "
            "e perfil fiscal desta nota."
        ),
        "hint": "Revise a matriz ISS em Fiscal → Regras ou Readiness antes de emitir.",
    },
    "MUNICIPIO_NAO_ADERENTE": {
        "title": "Município não conveniado",
        "message": "O município informado não está habilitado para emissão no Ambiente Nacional.",
        "hint": "Confirme o código IBGE do prestador e o convênio do município.",
    },
    "SEFIN_TRANSPORT": {
        "title": "Falha de comunicação com a SEFIN",
        "message": "Não foi possível concluir o envio por instabilidade ou indisponibilidade temporária.",
        "hint": "Aguarde alguns minutos e consulte o status. Se persistir, verifique certificado e conectividade.",
    },
    "SEFIN_TIMEOUT_BUDGET": {
        "title": "Tempo esgotado na SEFIN",
        "message": "A consulta de status excedeu o tempo limite configurado.",
        "hint": "Atualize o status da nota ou reenvie após confirmar que a DPS não ficou autorizada.",
    },
    "SEFIN_REJECTED": {
        "title": "Recusa da SEFIN Nacional",
        "message": "A DPS foi recusada pelo Ambiente Nacional sem código detalhado.",
        "hint": "Revise tomador, serviço, NBS, valores e tributação; em seguida emita novamente.",
    },
    "OPERATION_KIND_BLOCKED": {
        "title": "Operação não permitida",
        "message": "Este tipo de emissão está bloqueado para o tenant ou ambiente atual.",
        "hint": "Verifique flags do tenant e configuração do módulo NFS-e.",
    },
    "rtc_error": {
        "title": "Erro na classificação tributária (RTC)",
        "message": "A engine RTC não conseguiu classificar a operação para esta nota.",
        "hint": "Revise perfil fiscal, serviço e parâmetros da reforma tributária.",
    },
    "rtc_classification_unresolved": {
        "title": "Classificação RTC pendente",
        "message": "Não foi possível resolver a classificação RTC exigida para a emissão.",
        "hint": "Complete o cadastro fiscal do serviço e do perfil antes de reenviar.",
    },
}

# Códigos E* frequentes — Anexo/API NFS-e Nacional (mensagem oficial complementa quando existir).
_SEFIN_E_HINTS: dict[str, dict[str, str]] = {
    "E001": {
        "title": "DPS inválida",
        "message": "A Declaração de Prestação de Serviço não passou na validação inicial da SEFIN.",
        "hint": "Confira campos obrigatórios, formatos e consistência dos dados antes de reenviar.",
    },
    "E0120": {
        "title": "Inscrição municipal",
        "message": "Inscrição municipal ausente, inválida ou incompatível com o município emissor.",
        "hint": "Atualize o cadastro do prestador (IM) conforme exigência do município.",
    },
    "E0207": {
        "title": "Tomador ou prestador inconsistente",
        "message": (
            "CPF/CNPJ ou dados cadastrais do tomador/prestador divergem da base "
            "da Receita Federal."
        ),
        "hint": "Revise documento e nome do tomador; para CNPJ, use consulta Receita no cadastro.",
    },
}


def nf_status_label(status: str | None) -> str:
    code = (status or "").strip().lower()
    if not code:
        return "—"
    return _STATUS_LABELS.get(code, code.replace("_", " ").capitalize())


def nf_actor_label(actor: str | None) -> str:
    raw = (actor or "").strip()
    if not raw:
        return "—"
    key = raw.lower()
    if key in _ACTOR_LABELS:
        return _ACTOR_LABELS[key]
    if "@" in raw:
        return f"Usuário ({raw})"
    return raw.replace("_", " ").capitalize()


def _extract_sefin_error(raw: dict | None) -> tuple[str, str]:
    if not isinstance(raw, dict):
        return "", ""
    erros = raw.get("erros") or raw.get("errors") or []
    if isinstance(erros, list) and erros:
        first = erros[0]
        if isinstance(first, dict):
            code = str(first.get("codigo") or first.get("Codigo") or first.get("code") or "")
            msg = str(
                first.get("mensagem")
                or first.get("Mensagem")
                or first.get("message")
                or ""
            ).strip()
            return code, msg
        if isinstance(first, str):
            return "", first.strip()
    err = raw.get("error")
    if err:
        return "", str(err).strip()[:500]
    return "", ""


def rejection_display(issue: NfIssue) -> dict[str, str] | None:
    """Resumo amigável de rejeição/falha para UI."""
    code = (issue.rejection_code or "").strip()
    if not code and issue.status not in {
        NfIssue.Status.REJECTED,
        NfIssue.Status.FAILED,
    }:
        return None
    if not code:
        code = issue.status

    raw = issue.focus_status_raw if isinstance(issue.focus_status_raw, dict) else {}
    sefin_code, sefin_msg = _extract_sefin_error(raw)
    technical = code
    if sefin_code and sefin_code != code:
        technical = f"{code} / {sefin_code}"

    if code in _INTERNAL_REJECTIONS:
        block = _INTERNAL_REJECTIONS[code]
        message = block["message"]
        if sefin_msg and code not in {"SEFIN_REJECTED", "SEFIN_TRANSPORT"}:
            message = f"{message} Detalhe SEFIN: {sefin_msg}"
        return {
            "title": block["title"],
            "message": message,
            "hint": block["hint"],
            "code": technical,
        }

    lookup = sefin_code or code
    if lookup in _SEFIN_E_HINTS:
        block = _SEFIN_E_HINTS[lookup]
        message = block["message"]
        if sefin_msg:
            message = sefin_msg
        return {
            "title": block["title"],
            "message": message,
            "hint": block["hint"],
            "code": lookup,
        }

    if lookup.upper().startswith("E") and sefin_msg:
        return {
            "title": "Recusa da SEFIN Nacional",
            "message": sefin_msg,
            "hint": "Corrija os dados indicados e emita uma nova NFS-e.",
            "code": lookup,
        }

    return {
        "title": "Emissão não concluída",
        "message": sefin_msg or f"O processo retornou o código {code}.",
        "hint": "Se o problema persistir, contate o suporte informando a referência da nota.",
        "code": technical,
    }


def enrich_issue_events(events) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ev in events:
        rows.append(
            {
                "occurred_at": ev.occurred_at,
                "from_status": ev.from_status,
                "to_status": ev.to_status,
                "from_label": nf_status_label(ev.from_status),
                "to_label": nf_status_label(ev.to_status),
                "actor_label": nf_actor_label(ev.actor),
            }
        )
    return rows
