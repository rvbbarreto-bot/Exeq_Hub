"""Motor de conversa guiada — Fase 1 do canal WhatsApp (QA WA-FLX).

Fluxo: documento do tomador → (nome, se novo) → serviço → valor → resumo com
ISS calculado → CONFIRMAR/CANCELAR → emissão via `create_nf_issue` idempotente.
ISS nunca é perguntado: vem da regra municipal publicada (WA-FLX-05).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.channel.models import ChannelSession
from apps.fiscal.exceptions import (
    NationalCatalogError,
    RtcClassificationError,
    TaxRuleNotFoundError,
)
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.issuance.exceptions import FiscalProfileRequiredError
from apps.channel.webhook import mask_phone, mask_sensitive
from apps.master_data.models import Customer, Provider, ServiceCatalogItem
from apps.master_data.services import create_customer
from shared.validators import validate_cnpj, validate_cpf

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (
    ChannelSession.Status.COLLECTING,
    ChannelSession.Status.READY_TO_CONFIRM,
)
CONFIRM_WORDS = {"confirmar", "confirmo", "sim"}
CANCEL_WORDS = {"cancelar", "cancelo", "nao", "não"}
MAX_TRACKED_MESSAGE_IDS = 50

MSG_UNAUTHORIZED = (
    "Este número não está autorizado a emitir notas neste canal. "
    "Fale com o responsável pela sua conta EXEQ."
)
MSG_GREETING = (
    "Olá! Vou te ajudar a emitir sua NFS-e.\n"
    "Qual o CPF ou CNPJ do tomador (cliente da nota)?"
)
MSG_INVALID_DOCUMENT = "Documento inválido. Envie um CPF (11 dígitos) ou CNPJ (14 dígitos) válido."
MSG_ASK_NAME = "Tomador ainda não cadastrado. Qual o nome / razão social?"
MSG_INVALID_NAME = "Nome muito curto. Envie o nome ou a razão social do tomador."
MSG_INVALID_SERVICE = "Opção inválida. Responda com o número de um dos serviços listados."
MSG_ASK_AMOUNT = "Qual o valor do serviço? (ex.: 1.500,00)"
MSG_INVALID_AMOUNT = "Valor inválido. Envie apenas o valor, ex.: 1.500,00"
MSG_CANCELLED = "Emissão cancelada. Quando precisar, é só chamar de novo."
MSG_CONFIRM_HINT = "Responda CONFIRMAR para emitir ou CANCELAR para desistir."
MSG_NO_SERVICES = "Nenhum serviço cadastrado para emissão. Fale com o suporte EXEQ."
MSG_TENANT_MISCONFIGURED = (
    "Cadastro do prestador incompleto para emissão. Fale com o suporte EXEQ."
)


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _session_ttl() -> timedelta:
    return timedelta(minutes=int(getattr(settings, "CHANNEL_SESSION_TTL_MINUTES", 30)))


def is_phone_authorized(tenant, phone_e164: str) -> bool:
    """WA-FLX-08 — v1: apenas números na lista do tenant emitem pelo canal."""
    allowed = (tenant.settings or {}).get("whatsapp_authorized_phones") or []
    phone = _digits(phone_e164)
    return any(_digits(str(item)) == phone for item in allowed)


def _fmt_money(cents: int) -> str:
    value = f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {value}"


def _parse_document(text: str) -> tuple[str, str] | None:
    digits = _digits(text)
    try:
        if len(digits) == 11:
            return validate_cpf(digits), Customer.DocumentType.CPF
        if len(digits) == 14:
            return validate_cnpj(digits), Customer.DocumentType.CNPJ
    except ValueError:
        return None
    return None


def _parse_amount_cents(text: str) -> int | None:
    raw = (text or "").strip().replace("R$", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    cents = int((value * 100).to_integral_value())
    if cents < 1:
        return None
    return cents


def _services(tenant) -> list[ServiceCatalogItem]:
    return list(
        ServiceCatalogItem.objects.filter(tenant=tenant).order_by("service_code")
    )


def _service_menu(services: list[ServiceCatalogItem]) -> str:
    lines = ["Qual o serviço? Responda com o número:"]
    for i, svc in enumerate(services, start=1):
        lines.append(f"{i} - {svc.description} ({svc.service_code})")
    return "\n".join(lines)


def _published_rule(tenant, fiscal_profile, service_code: str) -> MunicipalTaxRule | None:
    from apps.fiscal.readiness import has_published_rule, provider_ibge

    provider = Provider.objects.filter(tenant=tenant).order_by("created_at").first()
    ibge = provider_ibge(provider) if provider else ""
    if fiscal_profile is None or not ibge:
        # fallback legado: qualquer regra do service no catálogo published
        return (
            MunicipalTaxRule.objects.filter(
                tenant=tenant,
                catalog__status=TaxRuleCatalog.Status.PUBLISHED,
                fiscal_profile=fiscal_profile,
                service_code=service_code,
            )
            .order_by("priority", "-valid_from")
            .first()
        )
    return has_published_rule(
        tenant=tenant,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge,
        service_code=service_code,
    )


def _emission_defaults(tenant) -> tuple[Provider | None, FiscalProfile | None]:
    provider = Provider.objects.filter(tenant=tenant).order_by("created_at").first()
    profile = (
        FiscalProfile.objects.filter(tenant=tenant, status="active")
        .order_by("created_at")
        .first()
    )
    return provider, profile


def _summary(flow: dict) -> str:
    iss_line = ""
    if flow.get("iss_cents") is not None:
        rate_pct = Decimal(str(flow.get("iss_rate", "0"))) * 100
        iss_line = f"\nISS estimado: {_fmt_money(int(flow['iss_cents']))} ({rate_pct:.2f}%)"
    return (
        "Confira os dados da NFS-e:\n"
        f"Tomador: {flow['customer_name']}\n"
        f"Serviço: {flow['service_label']}\n"
        f"Valor: {_fmt_money(int(flow['amount_cents']))}\n"
        f"Competência: {flow['competence_label']}"
        f"{iss_line}\n\n{MSG_CONFIRM_HINT}"
    )


def _expire_stale(tenant, phone_e164: str) -> None:
    """WA-FLX-07 — sessão parada além do TTL expira; conversa nova começa limpa."""
    cutoff = timezone.now() - _session_ttl()
    ChannelSession.objects.filter(
        tenant=tenant,
        phone_e164=phone_e164,
        status__in=ACTIVE_STATUSES,
        last_message_at__lt=cutoff,
    ).update(status=ChannelSession.Status.EXPIRED)


@transaction.atomic
def process_inbound(*, tenant, phone_e164: str, message_id: str, text: str):
    """Processa uma mensagem do canal e devolve (sessão, resposta ao usuário).

    Resposta vazia significa mensagem duplicada (webhook retry) — não responder.
    """
    if not is_phone_authorized(tenant, phone_e164):
        logger.info(
            "channel.engine unauthorized phone tenant=%s phone=%s",
            tenant.slug,
            mask_phone(phone_e164),
        )
        return None, MSG_UNAUTHORIZED

    _expire_stale(tenant, phone_e164)

    session = (
        ChannelSession.objects.select_for_update()
        .filter(tenant=tenant, phone_e164=phone_e164, status__in=ACTIVE_STATUSES)
        .order_by("-last_message_at")
        .first()
    )

    if session is None:
        recent_emitted = (
            ChannelSession.objects.filter(
                tenant=tenant,
                phone_e164=phone_e164,
                status=ChannelSession.Status.EMITTED,
                last_message_at__gte=timezone.now() - _session_ttl(),
            )
            .order_by("-last_message_at")
            .first()
        )
        # WA-FLX-06: CONFIRMAR repetido após emitir não cria nova conversa.
        if recent_emitted and (text or "").strip().lower() in CONFIRM_WORDS:
            ref = getattr(recent_emitted.nf_issue, "focus_ref", "") or ""
            return recent_emitted, f"Sua NFS-e já foi emitida. Ref: {ref}".strip()
        session = ChannelSession.objects.create(
            tenant=tenant,
            idempotency_key=f"{phone_e164}:{message_id}",
            phone_e164=phone_e164,
            draft_payload={"flow": {}, "message_ids": []},
            last_message_at=timezone.now(),
        )

    payload = dict(session.draft_payload or {})
    message_ids = list(payload.get("message_ids") or [])
    if message_id in message_ids:
        return session, ""
    message_ids.append(message_id)
    payload["message_ids"] = message_ids[-MAX_TRACKED_MESSAGE_IDS:]
    payload["text"] = text

    reply = _advance(session, payload, (text or "").strip())

    session.draft_payload = payload
    session.last_message_at = timezone.now()
    session.save(
        update_fields=["draft_payload", "status", "nf_issue", "last_message_at", "updated_at"]
    )
    return session, reply


def _advance(session: ChannelSession, payload: dict, text: str) -> str:
    from apps.channel.ai import handle_ai_turn

    flow = payload.setdefault("flow", {})
    lowered = text.lower()

    ai_reply = handle_ai_turn(session=session, payload=payload, text=text)
    if ai_reply is not None:
        return ai_reply

    if session.status == ChannelSession.Status.READY_TO_CONFIRM:
        if lowered in CONFIRM_WORDS:
            return _emit(session, flow)
        if lowered in CANCEL_WORDS:
            session.status = ChannelSession.Status.CANCELLED
            return MSG_CANCELLED
        return _summary(flow)

    step = flow.get("step") or ""

    if not step:
        flow["step"] = "document"
        return MSG_GREETING

    if step == "document":
        parsed = _parse_document(text)
        if parsed is None:
            return MSG_INVALID_DOCUMENT
        document, doc_type = parsed
        flow["document"] = document
        flow["document_type"] = doc_type
        customer = Customer.objects.filter(
            tenant=session.tenant, document=document
        ).first()
        if customer is not None:
            flow["customer_id"] = str(customer.id)
            flow["customer_name"] = customer.name
            return _goto_service(session, flow)
        flow["step"] = "name"
        return MSG_ASK_NAME

    if step == "name":
        name = text.strip()
        if len(name) < 3:
            return MSG_INVALID_NAME
        # WA-FLX-09 — tomador novo: get-or-create respeitando (tenant, document).
        customer = create_customer(
            tenant=session.tenant,
            document=flow["document"],
            document_type=flow["document_type"],
            name=name,
        )
        flow["customer_id"] = str(customer.id)
        flow["customer_name"] = customer.name
        return _goto_service(session, flow)

    if step == "service":
        services = _services(session.tenant)
        if not services:
            return MSG_NO_SERVICES
        choice = None
        if text.isdigit() and 1 <= int(text) <= len(services):
            choice = services[int(text) - 1]
        else:
            choice = next((s for s in services if s.service_code == text), None)
        if choice is None:
            return f"{MSG_INVALID_SERVICE}\n\n{_service_menu(services)}"
        flow["service_id"] = str(choice.id)
        flow["service_label"] = f"{choice.description} ({choice.service_code})"
        # WA-IA: valor já detectado na frase livre — pula pergunta e vai ao resumo.
        hint = flow.pop("amount_hint_cents", None)
        if hint:
            flow["amount_cents"] = int(hint)
            return _goto_confirm(session, flow)
        flow["step"] = "amount"
        return MSG_ASK_AMOUNT

    if step == "amount":
        cents = _parse_amount_cents(text)
        if cents is None:
            return MSG_INVALID_AMOUNT
        flow["amount_cents"] = cents
        return _goto_confirm(session, flow)

    flow["step"] = "document"
    return MSG_GREETING


def _goto_service(session: ChannelSession, flow: dict) -> str:
    services = _services(session.tenant)
    if not services:
        return MSG_NO_SERVICES
    flow["step"] = "service"
    return _service_menu(services)


def _goto_confirm(session: ChannelSession, flow: dict) -> str:
    """Monta o resumo: ISS calculado pela regra publicada — nunca perguntado."""
    tenant = session.tenant
    provider, profile = _emission_defaults(tenant)
    if provider is None or profile is None:
        return MSG_TENANT_MISCONFIGURED

    service = ServiceCatalogItem.objects.get(pk=flow["service_id"], tenant=tenant)
    rule = _published_rule(tenant, profile, service.service_code)
    competence = date.today().replace(day=1)

    flow["provider_id"] = str(provider.id)
    flow["fiscal_profile_id"] = str(profile.id)
    flow["competence_date"] = competence.isoformat()
    flow["competence_label"] = competence.strftime("%m/%Y")
    if rule is not None:
        flow["ibge_code"] = rule.ibge_code
        flow["iss_rate"] = str(rule.iss_rate)
        flow["iss_cents"] = int(
            (Decimal(flow["amount_cents"]) * rule.iss_rate).to_integral_value()
        )
    else:
        flow["ibge_code"] = ""
        flow["iss_rate"] = "0"
        flow["iss_cents"] = None

    flow["step"] = "confirm"
    session.status = ChannelSession.Status.READY_TO_CONFIRM
    return _summary(flow)


def _emit(session: ChannelSession, flow: dict) -> str:
    from apps.issuance.services import create_nf_issue

    tenant = session.tenant
    try:
        provider = Provider.objects.get(pk=flow["provider_id"], tenant=tenant)
        profile = FiscalProfile.objects.get(pk=flow["fiscal_profile_id"], tenant=tenant)
        customer = Customer.objects.get(pk=flow["customer_id"], tenant=tenant)
        service = ServiceCatalogItem.objects.get(pk=flow["service_id"], tenant=tenant)
    except (
        Provider.DoesNotExist,
        FiscalProfile.DoesNotExist,
        Customer.DoesNotExist,
        ServiceCatalogItem.DoesNotExist,
    ):
        return MSG_TENANT_MISCONFIGURED

    if not flow.get("ibge_code"):
        session.status = ChannelSession.Status.CANCELLED
        return (
            "Configuração fiscal incompleta (sem regra ISS publicada para este "
            "serviço no município do prestador). Emissão não realizada — "
            "ajuste em Hub → Fiscal → Pronto para emitir."
        )

    try:
        from apps.fiscal.readiness import FiscalReadinessError, assert_emit_rule_cover

        assert_emit_rule_cover(
            tenant=tenant,
            fiscal_profile=profile,
            ibge_code=flow["ibge_code"],
            service_code=service.service_code,
            competence_date=date.fromisoformat(flow["competence_date"]),
            service=service,
        )
    except FiscalReadinessError as exc:
        session.status = ChannelSession.Status.CANCELLED
        return f"Configuração fiscal incompleta: {exc}"

    try:
        issue = create_nf_issue(
            tenant=tenant,
            idempotency_key=f"wa:{session.id}",
            provider=provider,
            customer=customer,
            service=service,
            fiscal_profile=profile,
            ibge_code=flow["ibge_code"],
            competence_date=date.fromisoformat(flow["competence_date"]),
            amount_cents=int(flow["amount_cents"]),
        )
    except (
        TaxRuleNotFoundError,
        NationalCatalogError,
        RtcClassificationError,
        FiscalProfileRequiredError,
    ) as exc:
        # WA-FLX-10 — falha fiscal: sessão não fica emitted; erro auditado no log.
        logger.warning(
            "channel.engine emit failed session=%s err=%s",
            session.id,
            mask_sensitive(str(exc)),
        )
        session.status = ChannelSession.Status.CANCELLED
        return f"Não foi possível emitir a NFS-e: {exc}"

    issue.refresh_from_db()
    session.nf_issue = issue
    if issue.status in {"rejected", "failed"}:
        session.status = ChannelSession.Status.CANCELLED
        code = issue.rejection_code or issue.status
        return (
            f"A emissão foi recusada ({code}). "
            "Nenhuma nota foi gerada — fale com o suporte EXEQ."
        )

    session.status = ChannelSession.Status.EMITTED
    ref = issue.focus_ref or str(issue.id)
    return (
        f"NFS-e solicitada com sucesso. Ref: {ref}\n"
        "Você receberá os arquivos assim que a nota for autorizada."
    )
