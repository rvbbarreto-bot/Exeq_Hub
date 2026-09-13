"""Webhook Evolution — Fase 3 (WA-SEC): auth, payload nativo, tenant por instância."""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.accounts.models import Tenant

logger = logging.getLogger(__name__)

_DOC_RE = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b")


@dataclass(frozen=True)
class InboundMessage:
    tenant: Tenant
    phone_e164: str
    message_id: str
    text: str
    instance: str = ""
    event: str = ""


@dataclass(frozen=True)
class ParseOutcome:
    """ok | ignored (200 sem processar) | reject (400/404)."""

    status: str
    inbound: InboundMessage | None = None
    reason: str = ""


def mask_sensitive(text: str) -> str:
    """WA-SEC-05 — mascara CPF/CNPJ em textos de log."""
    if not text:
        return text

    def _repl(match: re.Match) -> str:
        digits = "".join(ch for ch in match.group(0) if ch.isdigit())
        if len(digits) < 5:
            return "***"
        return f"{digits[:3]}***{digits[-2:]}"

    return _DOC_RE.sub(_repl, text)


def mask_phone(phone_e164: str) -> str:
    digits = "".join(ch for ch in (phone_e164 or "") if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def extract_webhook_token(request) -> str:
    headers = request.headers
    token = (headers.get("X-Exeq-Webhook-Token") or headers.get("apikey") or "").strip()
    if token:
        return token
    auth = (headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def verify_webhook_token(request) -> bool:
    """WA-SEC-01 — token obrigatório no header (não confiar em apikey do body)."""
    expected = (getattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None) or "").strip()
    if not expected:
        logger.warning("channel.webhook token não configurado (EVOLUTION_WEBHOOK_TOKEN)")
        return False
    provided = extract_webhook_token(request)
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def resolve_tenant_by_instance(instance_name: str) -> Tenant | None:
    """WA-SEC-02 — tenant pela instância Evolution configurada no settings do tenant."""
    name = (instance_name or "").strip()
    if not name:
        return None
    return (
        Tenant.objects.filter(
            status=Tenant.Status.ACTIVE,
            settings__evolution_instance=name,
        )
        .order_by("created_at")
        .first()
    )


def _jid_to_e164(jid: str) -> str:
    raw = (jid or "").split("@")[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    return f"+{digits}"


def _extract_text(message: dict | None) -> str:
    if not isinstance(message, dict):
        return ""
    if message.get("conversation"):
        return str(message["conversation"])
    ext = message.get("extendedTextMessage") or {}
    if isinstance(ext, dict) and ext.get("text"):
        return str(ext["text"])
    ephemeral = message.get("ephemeralMessage") or {}
    if isinstance(ephemeral, dict):
        inner = ephemeral.get("message") or {}
        return _extract_text(inner if isinstance(inner, dict) else None)
    return ""


def _is_messages_upsert(event: str) -> bool:
    normalized = (event or "").strip().lower().replace("_", ".")
    return normalized in {"messages.upsert", "message.upsert"}


def parse_inbound_payload(payload: dict[str, Any]) -> ParseOutcome:
    """Aceita payload nativo Evolution ou legado simplificado (lab).

    Com payload nativo, o tenant vem da instância — `tenant_slug` do body é ignorado.
    """
    if not isinstance(payload, dict):
        return ParseOutcome("reject", reason="payload_invalido")

    event = str(payload.get("event") or "")
    instance = str(payload.get("instance") or "").strip()
    data = payload.get("data")
    native_shape = bool(instance) or _is_messages_upsert(event) or isinstance(data, dict)

    if native_shape:
        if event and not _is_messages_upsert(event):
            return ParseOutcome("ignored", reason=f"evento_ignorado:{event}")
        if not isinstance(data, dict):
            return ParseOutcome("reject", reason="payload_incompleto")
        key = data.get("key") or {}
        if not isinstance(key, dict):
            return ParseOutcome("reject", reason="payload_incompleto")
        if key.get("fromMe"):
            return ParseOutcome("ignored", reason="from_me")
        tenant = resolve_tenant_by_instance(instance)
        if tenant is None:
            logger.warning(
                "channel.webhook instância sem tenant instance=%s",
                instance or "?",
            )
            return ParseOutcome("reject", reason="instancia_desconhecida")
        phone = _jid_to_e164(str(key.get("remoteJid") or payload.get("sender") or ""))
        message_id = str(key.get("id") or "").strip()
        msg = data.get("message") if isinstance(data.get("message"), dict) else None
        text = _extract_text(msg)
        if not phone or not message_id:
            return ParseOutcome("reject", reason="payload_incompleto")
        return ParseOutcome(
            "ok",
            inbound=InboundMessage(
                tenant=tenant,
                phone_e164=phone,
                message_id=message_id,
                text=text,
                instance=instance,
                event=event or "messages.upsert",
            ),
        )

    if not getattr(settings, "EVOLUTION_WEBHOOK_ALLOW_LEGACY", True):
        return ParseOutcome("reject", reason="legacy_desabilitado")

    tenant_slug = str(payload.get("tenant_slug") or "").strip()
    phone = str(payload.get("phone_e164") or "").strip()
    message_id = str(payload.get("message_id") or "").strip()
    text = str(payload.get("text") or "")
    if not tenant_slug or not phone or not message_id:
        return ParseOutcome("reject", reason="payload_incompleto")
    try:
        tenant = Tenant.objects.get(slug=tenant_slug, status=Tenant.Status.ACTIVE)
    except Tenant.DoesNotExist:
        return ParseOutcome("reject", reason="tenant_invalido")
    return ParseOutcome(
        "ok",
        inbound=InboundMessage(
            tenant=tenant,
            phone_e164=phone,
            message_id=message_id,
            text=text,
            event="legacy",
        ),
    )
