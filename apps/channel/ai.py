"""Camada WA-IA — intérprete conversacional com ferramentas determinísticas.

Princípio (ARD): a IA entende intenção/slots; emissão, busca, reenvio e cancelamento
só executam via serviços do Hub. Stub heurístico é o default de lab (sem LLM);
`CHANNEL_AI_MODE=off` desliga e mantém só o fluxo guiado.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db.models import Q

from apps.channel.webhook import mask_sensitive
from apps.issuance.models import NfIssue
from apps.master_data.models import Customer, ServiceCatalogItem
from shared.validators import validate_cnpj, validate_cpf

logger = logging.getLogger(__name__)

INJECTION_MARKERS = (
    "ignore as regras",
    "ignore as instrucoes",
    "ignore as instruções",
    "sem confirmar",
    "sem confirmacao",
    "sem confirmação",
    "emita sem",
    "cancela sem",
)

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


@dataclass
class AgentIntent:
    name: str  # emit | search | resend | cancel | unknown
    slots: dict[str, Any] = field(default_factory=dict)
    injection_attempt: bool = False


def ai_enabled() -> bool:
    mode = (getattr(settings, "CHANNEL_AI_MODE", "stub") or "stub").strip().lower()
    return mode not in {"", "off", "false", "0"}


def interpret(text: str) -> AgentIntent:
    """Stub heurístico — substitui LLM em lab; mesma interface para futuro HTTP."""
    raw = (text or "").strip()
    lowered = raw.lower()
    injection = any(m in lowered for m in INJECTION_MARKERS)

    slots: dict[str, Any] = {}
    doc = _extract_document(raw)
    if doc:
        slots["document"] = doc[0]
        slots["document_type"] = doc[1]
    amount = _extract_amount(raw)
    if amount is not None:
        slots["amount_cents"] = amount
    period = _extract_period(lowered)
    if period:
        slots["year"] = period[0]
        slots["month"] = period[1]
    ref = _extract_ref(raw)
    if ref:
        slots["focus_ref"] = ref

    if any(
        k in lowered
        for k in ("deletar", "deleta", "delete", "apagar", "apaga", "excluir", "cancela", "cancelar")
    ):
        return AgentIntent("cancel", slots, injection_attempt=injection)
    if any(
        k in lowered
        for k in (
            "manda de novo",
            "reenviar",
            "reenvie",
            "envia o pdf",
            "manda o pdf",
            "manda o xml",
        )
    ):
        return AgentIntent("resend", slots, injection_attempt=injection)
    if any(
        k in lowered
        for k in (
            "buscar",
            "busca",
            "mostra",
            "listar",
            "listagem",
            "notas de",
            "histórico",
            "historico",
        )
    ):
        return AgentIntent("search", slots, injection_attempt=injection)
    if any(
        k in lowered
        for k in (
            "emitir",
            "emite",
            "emita",
            "emissao",
            "emissão",
            "nota fiscal",
            "nfs-e",
            "nfse",
            "quero nota",
        )
    ):
        return AgentIntent("emit", slots, injection_attempt=injection)
    return AgentIntent("unknown", slots, injection_attempt=injection)


def handle_ai_turn(*, session, payload: dict, text: str) -> str | None:
    """Retorna resposta IA ou None para cair no fluxo guiado (WA-IA-05)."""
    if not ai_enabled():
        return None

    flow = payload.setdefault("flow", {})
    if flow.get("ai_pending_cancel"):
        return _handle_pending_cancel(session, flow, text)

    # Em confirmação de emissão, só o motor guiado (CONFIRMAR/CANCELAR) age.
    if session.status == session.Status.READY_TO_CONFIRM:
        return None

    intent = interpret(text)
    if intent.injection_attempt and intent.name in {"emit", "cancel"}:
        logger.warning(
            "channel.ai injection blocked session=%s intent=%s text=%s",
            session.id,
            intent.name,
            mask_sensitive(text)[:80],
        )
        return (
            "Não posso executar atos fiscais sem confirmação explícita. "
            "Use o fluxo normal: informe os dados e responda CONFIRMAR no resumo."
        )

    if intent.name == "unknown":
        return None

    # Busca / reenvio / cancelamento podem interromper coleta; emissão não.
    step = flow.get("step") or ""
    if intent.name == "emit" and step in {"document", "name", "service", "amount", "confirm"}:
        return None

    if intent.name == "search":
        return _tool_search(session.tenant, intent.slots)
    if intent.name == "resend":
        return _tool_resend(session, intent.slots)
    if intent.name == "cancel":
        return _tool_cancel_prepare(session, flow, intent.slots)
    if intent.name == "emit":
        return _tool_emit_seed(session, flow, intent.slots)
    return None


def _extract_document(text: str) -> tuple[str, str] | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    for length, kind, validator in (
        (14, "cnpj", validate_cnpj),
        (11, "cpf", validate_cpf),
    ):
        for i in range(0, max(len(digits) - length + 1, 0)):
            chunk = digits[i : i + length]
            if len(chunk) != length:
                continue
            try:
                return validator(chunk), kind
            except ValueError:
                continue
    return None


def _extract_amount(text: str) -> int | None:
    match = re.search(
        r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:[.,]\d{2})?)",
        text.lower(),
    )
    if not match:
        return None
    raw = match.group(1)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        cents = int((Decimal(raw) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None
    return cents if cents >= 1 else None


def _extract_period(lowered: str) -> tuple[int, int] | None:
    year = date.today().year
    ymatch = re.search(r"\b(20\d{2})\b", lowered)
    if ymatch:
        year = int(ymatch.group(1))
    for name, month in MONTHS.items():
        if name in lowered:
            return year, month
    mm = re.search(r"\b(0?[1-9]|1[0-2])/(20\d{2})\b", lowered)
    if mm:
        return int(mm.group(2)), int(mm.group(1))
    return None


def _extract_ref(text: str) -> str:
    match = re.search(r"\b(SEFIN-[A-Za-z0-9_-]+|FOCUS-[A-Za-z0-9_-]+)\b", text)
    return match.group(1) if match else ""


def _fmt_money(cents: int) -> str:
    value = f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {value}"


def _service_menu(tenant) -> str:
    services = list(ServiceCatalogItem.objects.filter(tenant=tenant).order_by("service_code"))
    if not services:
        return "Nenhum serviço cadastrado para emissão. Fale com o suporte EXEQ."
    lines = ["Qual o serviço? Responda com o número:"]
    for i, svc in enumerate(services, start=1):
        lines.append(f"{i} - {svc.description} ({svc.service_code})")
    return "\n".join(lines)


def _tool_search(tenant, slots: dict) -> str:
    """WA-IA-04 — busca no escopo do tenant, limite ARD §12."""
    qs = NfIssue.objects.filter(tenant=tenant).order_by("-competence_date", "-created_at")
    year = slots.get("year")
    month = slots.get("month")
    if year and month:
        qs = qs.filter(competence_date__year=year, competence_date__month=month)
    issues = list(qs[:24])
    if not issues:
        period = f" de {month:02d}/{year}" if year and month else ""
        return f"Nenhuma NFS-e encontrada{period} neste período."
    lines = ["Notas encontradas (máx. 24):"]
    for issue in issues:
        ref = issue.focus_ref or str(issue.id)[:8]
        lines.append(
            f"- {issue.competence_date:%m/%Y} | {issue.status} | "
            f"{_fmt_money(issue.amount_cents)} | Ref: {ref}"
        )
    return "\n".join(lines)


def _resolve_issue(tenant, slots: dict) -> NfIssue | None:
    ref = slots.get("focus_ref") or ""
    qs = NfIssue.objects.filter(tenant=tenant)
    if ref:
        found = qs.filter(Q(focus_ref=ref) | Q(focus_ref__icontains=ref)).order_by(
            "-created_at"
        ).first()
        if found:
            return found
    return qs.order_by("-created_at").first()


def _tool_resend(session, slots: dict) -> str:
    from apps.channel.services import MediaDeliveryError, deliver_nf_artifacts

    issue = _resolve_issue(session.tenant, slots)
    if issue is None:
        return "Não encontrei NFS-e para reenviar."
    if issue.status != NfIssue.Status.AUTHORIZED:
        return (
            f"A nota Ref {issue.focus_ref or issue.id} não está autorizada "
            f"(status: {issue.status})."
        )
    try:
        deliver_nf_artifacts(
            tenant=session.tenant,
            nf_issue=issue,
            phone_e164=session.phone_e164,
            session=session,
        )
    except MediaDeliveryError as exc:
        return f"Falha ao reenviar arquivos: {exc}"
    return f"Reenviei PDF e XML da NFS-e Ref: {issue.focus_ref or issue.id}."


def _tool_cancel_prepare(session, flow: dict, slots: dict) -> str:
    """WA-IA-03 — 'deletar' vira cancelamento com confirmação reforçada."""
    issue = _resolve_issue(session.tenant, slots)
    if issue is None:
        return "Não encontrei NFS-e para cancelar."
    if issue.status == NfIssue.Status.CANCELLED:
        return f"A nota Ref {issue.focus_ref or issue.id} já está cancelada."
    if issue.status != NfIssue.Status.AUTHORIZED:
        return f"Só cancelo notas autorizadas. Status atual: {issue.status}."
    flow["ai_pending_cancel"] = str(issue.id)
    flow["step"] = "ai_cancel_confirm"
    return (
        "Cancelamento fiscal (não exclusão).\n"
        f"Nota: Ref {issue.focus_ref or issue.id} | "
        f"{issue.competence_date:%m/%Y} | {_fmt_money(issue.amount_cents)}\n\n"
        "Para confirmar, responda: CONFIRMAR CANCELAMENTO\n"
        "Para desistir: CANCELAR"
    )


def _handle_pending_cancel(session, flow: dict, text: str) -> str:
    from apps.issuance.exceptions import (
        CancelJustificationError,
        FocusCancelFailedError,
        InvalidTransitionError,
    )
    from apps.issuance.services import cancel_nf_issue

    lowered = (text or "").strip().lower()
    if lowered in {"cancelar", "nao", "não"}:
        flow.pop("ai_pending_cancel", None)
        flow["step"] = ""
        return "Cancelamento abortado. Nenhuma nota foi alterada."
    if lowered != "confirmar cancelamento":
        return "Para cancelar, responda exatamente: CONFIRMAR CANCELAMENTO"

    issue = NfIssue.objects.filter(
        tenant=session.tenant, id=flow.get("ai_pending_cancel")
    ).first()
    flow.pop("ai_pending_cancel", None)
    flow["step"] = ""
    if issue is None:
        return "Nota não encontrada para cancelamento."
    try:
        cancel_nf_issue(
            issue,
            justificativa="Cancelamento solicitado via canal WhatsApp (WA-IA).",
            actor="whatsapp_ai",
        )
    except (InvalidTransitionError, CancelJustificationError, FocusCancelFailedError) as exc:
        return f"Não foi possível cancelar: {exc}"
    issue.refresh_from_db()
    return f"NFS-e cancelada. Ref: {issue.focus_ref or issue.id}."


def _tool_emit_seed(session, flow: dict, slots: dict) -> str | None:
    """WA-IA-01 — preenche slots e devolve ao fluxo guiado para completar/confirmar."""
    if flow.get("step") in {"service", "amount", "name", "confirm"}:
        return None

    if slots.get("amount_cents"):
        flow["amount_hint_cents"] = slots["amount_cents"]

    if slots.get("document"):
        flow["document"] = slots["document"]
        flow["document_type"] = slots["document_type"]
        customer = Customer.objects.filter(
            tenant=session.tenant, document=slots["document"]
        ).first()
        if customer is not None:
            flow["customer_id"] = str(customer.id)
            flow["customer_name"] = customer.name
            flow["step"] = "service"
            return _service_menu(session.tenant)
        flow["step"] = "name"
        return "Tomador ainda não cadastrado. Qual o nome / razão social?"

    flow["step"] = "document"
    if slots.get("amount_cents"):
        return (
            "Vou emitir sua NFS-e. Qual o CPF ou CNPJ do tomador (cliente da nota)? "
            f"Valor detectado: {_fmt_money(slots['amount_cents'])}."
        )
    # Mesma saudação do fluxo guiado (compatível com WA-FLX-01).
    return (
        "Olá! Vou te ajudar a emitir sua NFS-e.\n"
        "Qual o CPF ou CNPJ do tomador (cliente da nota)?"
    )
