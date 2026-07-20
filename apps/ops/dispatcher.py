from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.ops.models import OutboxMessage

# Processados por workers de domínio dedicados (não pelo dispatcher genérico).
SKIP_EVENT_TYPES = frozenset({"nf_issue.queued"})

MAX_ATTEMPTS = 8


@transaction.atomic
def claim_and_dispatch(message_id: str) -> str:
    msg = (
        OutboxMessage.objects.select_for_update()
        .select_related("tenant")
        .filter(id=message_id)
        .first()
    )
    if msg is None:
        return "missing"
    if msg.status not in {
        OutboxMessage.Status.PENDING,
        OutboxMessage.Status.FAILED,
    }:
        return msg.status
    if msg.available_at > timezone.now():
        return "not_ready"
    if msg.event_type in SKIP_EVENT_TYPES:
        msg.status = OutboxMessage.Status.PROCESSED
        msg.processed_at = timezone.now()
        msg.save(update_fields=["status", "processed_at", "updated_at"])
        return "skipped"

    msg.status = OutboxMessage.Status.PROCESSING
    msg.attempts += 1
    msg.save(update_fields=["status", "attempts", "updated_at"])

    try:
        _handle(msg)
    except Exception as exc:  # noqa: BLE001 — outbox deve capturar e marcar failed/dead
        msg.last_error = str(exc)[:2000]
        if msg.attempts >= MAX_ATTEMPTS:
            msg.status = OutboxMessage.Status.DEAD
        else:
            msg.status = OutboxMessage.Status.FAILED
            msg.available_at = timezone.now() + timedelta(seconds=30 * msg.attempts)
        msg.save(
            update_fields=["status", "last_error", "available_at", "updated_at"]
        )
        return "failed"

    msg.status = OutboxMessage.Status.PROCESSED
    msg.processed_at = timezone.now()
    msg.last_error = ""
    msg.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
    return "processed"


def _handle(msg: OutboxMessage) -> None:
    handlers = {
        "nf_issue.authorized": _notify_nf_authorized,
        "charge.paid": _notify_charge_paid,
        "guia_fiscal.available": _notify_guia_available,
    }
    handler = handlers.get(msg.event_type)
    if handler is None:
        return
    handler(msg)


def _notify_phone(tenant) -> str:
    return str((tenant.settings or {}).get("notify_phone") or "").strip()


def _notify_nf_authorized(msg: OutboxMessage) -> None:
    phone = _notify_phone(msg.tenant)
    if not phone:
        return
    from apps.channel.services import enqueue_notification
    from apps.issuance.models import NfIssue

    issue = NfIssue.objects.filter(tenant=msg.tenant, id=msg.aggregate_id).first()
    ref = (msg.payload or {}).get("focus_ref") or (issue.focus_ref if issue else "")
    enqueue_notification(
        tenant=msg.tenant,
        phone_e164=phone,
        event_type=msg.event_type,
        message_body=f"NFS-e autorizada. Ref: {ref}",
        nf_issue=issue,
    )


def _notify_charge_paid(msg: OutboxMessage) -> None:
    phone = _notify_phone(msg.tenant)
    if not phone:
        return
    from apps.channel.services import enqueue_notification

    charge_id = (msg.payload or {}).get("charge_id") or str(msg.aggregate_id)
    enqueue_notification(
        tenant=msg.tenant,
        phone_e164=phone,
        event_type=msg.event_type,
        message_body=f"Cobrança paga: {charge_id}",
    )


def _notify_guia_available(msg: OutboxMessage) -> None:
    phone = _notify_phone(msg.tenant)
    if not phone:
        return
    from apps.channel.services import enqueue_notification

    enqueue_notification(
        tenant=msg.tenant,
        phone_e164=phone,
        event_type=msg.event_type,
        message_body=f"Guia fiscal disponível: {msg.aggregate_id}",
    )
