from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.ops.models import OutboxMessage

logger = logging.getLogger(__name__)

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
        "nfe.authorized": _notify_nfe_lifecycle,
        "nfe.rejected": _notify_nfe_lifecycle,
        "nfe.cancelled": _notify_nfe_lifecycle,
        "charge.paid": _notify_charge_paid,
        "guia_fiscal.available": _notify_guia_available,
        "appointment.pending": _notify_appointment,
        "appointment.confirmed": _notify_appointment,
        "appointment.cancelled": _notify_appointment,
        "appointment.completed": _notify_appointment,
        "certificate.expiring": _notify_certificate_alert,
        "certificate.expired": _notify_certificate_alert,
    }
    handler = handlers.get(msg.event_type)
    if handler is None:
        return
    handler(msg)


def _notify_phone(tenant) -> str:
    return str((tenant.settings or {}).get("notify_phone") or "").strip()


def _notify_appointment(msg: OutboxMessage) -> None:
    payload = msg.payload or {}
    phone = str(payload.get("phone_e164") or "").strip()
    body = str(payload.get("message_body") or "").strip()
    if not phone or not body:
        return
    from apps.channel.services import enqueue_notification

    enqueue_notification(
        tenant=msg.tenant,
        phone_e164=phone,
        event_type=msg.event_type,
        message_body=body,
    )


def _notify_nf_authorized(msg: OutboxMessage) -> None:
    """Ops notify_phone (texto) + solicitante do canal (PDF/XML — Fase 2 WA-ART)."""
    from apps.channel.models import ChannelSession
    from apps.channel.services import deliver_nf_artifacts, enqueue_notification
    from apps.issuance.models import NfIssue

    issue = NfIssue.objects.filter(tenant=msg.tenant, id=msg.aggregate_id).first()
    ref = (msg.payload or {}).get("focus_ref") or (issue.focus_ref if issue else "")

    session = None
    if issue is not None:
        session = (
            ChannelSession.objects.filter(
                tenant=msg.tenant,
                nf_issue=issue,
                status=ChannelSession.Status.EMITTED,
            )
            .order_by("-last_message_at")
            .first()
        )

    if session is not None and issue is not None:
        # WA-ART-01/03: entrega ao solicitante; falha de mídia → retry outbox.
        deliver_nf_artifacts(
            tenant=msg.tenant,
            nf_issue=issue,
            phone_e164=session.phone_e164,
            session=session,
        )
        ops_phone = _notify_phone(msg.tenant)
        if ops_phone and ops_phone != session.phone_e164:
            enqueue_notification(
                tenant=msg.tenant,
                phone_e164=ops_phone,
                event_type=msg.event_type,
                message_body=f"NFS-e autorizada. Ref: {ref}",
                nf_issue=issue,
            )
        return

    phone = _notify_phone(msg.tenant)
    if not phone:
        return
    enqueue_notification(
        tenant=msg.tenant,
        phone_e164=phone,
        event_type=msg.event_type,
        message_body=f"NFS-e autorizada. Ref: {ref}",
        nf_issue=issue,
    )


def _nfe_lifecycle_body(msg: OutboxMessage, inv) -> str:
    payload = msg.payload or {}
    key = (payload.get("access_key") or (inv.access_key if inv else "") or "")[:44]
    series = payload.get("series") if inv is None else inv.series
    number = payload.get("number") if inv is None else inv.number
    ref = f"{series}/{number}" if number is not None else (key or str(msg.aggregate_id)[:8])
    if msg.event_type == "nfe.authorized":
        return f"NF-e autorizada. {ref}" + (
            f" chave {key[:10]}…" if len(key) >= 10 else ""
        )
    if msg.event_type == "nfe.rejected":
        code = payload.get("rejection_code") or (inv.rejection_code if inv else "") or "—"
        return f"NF-e rejeitada. {ref} cStat={code}"
    if msg.event_type == "nfe.cancelled":
        return f"NF-e cancelada. {ref}" + (
            f" chave {key[:10]}…" if len(key) >= 10 else ""
        )
    return f"NF-e evento {msg.event_type}: {ref}"


def _notify_nfe_lifecycle(msg: OutboxMessage) -> None:
    """RF-70 texto; RF-72 mídia se sessão; RF-71 e-mail XML+DANFE em authorized."""
    from apps.channel.models import ChannelSession
    from apps.channel.services import deliver_nfe_artifacts, enqueue_notification
    from apps.nfe.models import NfeInvoice

    inv = NfeInvoice.objects.filter(tenant=msg.tenant, id=msg.aggregate_id).first()
    body = _nfe_lifecycle_body(msg, inv)[:1000]

    session = None
    if inv is not None and msg.event_type == "nfe.authorized":
        session = (
            ChannelSession.objects.filter(
                tenant=msg.tenant,
                nfe_invoice=inv,
                status=ChannelSession.Status.EMITTED,
            )
            .order_by("-last_message_at")
            .first()
        )

    if session is not None and inv is not None:
        # RF-72: entrega ao solicitante; falha de mídia → retry outbox.
        deliver_nfe_artifacts(
            tenant=msg.tenant,
            nfe_invoice=inv,
            phone_e164=session.phone_e164,
            session=session,
        )
        ops_phone = _notify_phone(msg.tenant)
        if ops_phone and ops_phone != session.phone_e164:
            enqueue_notification(
                tenant=msg.tenant,
                phone_e164=ops_phone,
                event_type=msg.event_type,
                message_body=body,
                nfe_invoice=inv,
            )
    else:
        phone = _notify_phone(msg.tenant)
        if phone:
            enqueue_notification(
                tenant=msg.tenant,
                phone_e164=phone,
                event_type=msg.event_type,
                message_body=body,
                nfe_invoice=inv,
            )

    # RF-71: e-mail não desfaz authorize; falha → retry outbox.
    if inv is not None and msg.event_type == "nfe.authorized":
        from apps.nfe.email_delivery import deliver_authorized_email

        deliver_authorized_email(
            invoice=inv,
            payload=msg.payload if isinstance(msg.payload, dict) else None,
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


def _notify_certificate_alert(msg: OutboxMessage) -> None:
    """M5 — alerta cert a vencer/expirado: log estruturado + WhatsApp se notify_phone."""
    payload = msg.payload or {}
    cnpj = payload.get("cnpj") or ""
    days_left = payload.get("days_left")
    status = payload.get("status") or msg.event_type
    not_after = payload.get("not_after") or ""
    logger.warning(
        "certificate.alert event=%s tenant=%s cnpj=%s status=%s days_left=%s not_after=%s",
        msg.event_type,
        msg.tenant_id,
        cnpj,
        status,
        days_left,
        not_after,
    )
    phone = _notify_phone(msg.tenant)
    if not phone:
        return
    from apps.channel.services import enqueue_notification

    label = "expirado" if msg.event_type == "certificate.expired" else "a vencer"
    enqueue_notification(
        tenant=msg.tenant,
        phone_e164=phone,
        event_type=msg.event_type,
        message_body=(
            f"Certificado digital {label}. CNPJ {cnpj}. "
            f"Validade: {not_after}. Dias restantes: {days_left}."
        ),
    )
