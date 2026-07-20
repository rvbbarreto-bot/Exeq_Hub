from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.channel.models import ChannelNotification, ChannelSession
from integrations.evolution.client import get_evolution_gateway

DEBOUNCE_SECONDS = 5


@transaction.atomic
def ingest_inbound_message(
    *,
    tenant,
    phone_e164: str,
    message_id: str,
    text: str,
) -> ChannelSession:
    """Debounce: mesma mensagem/janela curta atualiza uma sessão, não duplica."""
    idempotency_key = f"{phone_e164}:{message_id}"
    existing = ChannelSession.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        existing.draft_payload = {**(existing.draft_payload or {}), "text": text}
        existing.last_message_at = timezone.now()
        existing.save(update_fields=["draft_payload", "last_message_at", "updated_at"])
        return existing

    window_start = timezone.now() - timedelta(seconds=DEBOUNCE_SECONDS)
    recent = (
        ChannelSession.objects.select_for_update()
        .filter(
            tenant=tenant,
            phone_e164=phone_e164,
            status=ChannelSession.Status.COLLECTING,
            last_message_at__gte=window_start,
        )
        .order_by("-last_message_at")
        .first()
    )
    if recent:
        recent.draft_payload = {
            **(recent.draft_payload or {}),
            "text": text,
            "last_message_id": message_id,
        }
        recent.last_message_at = timezone.now()
        recent.save(update_fields=["draft_payload", "last_message_at", "updated_at"])
        return recent

    return ChannelSession.objects.create(
        tenant=tenant,
        idempotency_key=idempotency_key,
        phone_e164=phone_e164,
        draft_payload={"text": text, "last_message_id": message_id},
        last_message_at=timezone.now(),
    )


@transaction.atomic
def enqueue_notification(
    *,
    tenant,
    phone_e164: str,
    event_type: str,
    message_body: str,
    session: ChannelSession | None = None,
    nf_issue=None,
) -> ChannelNotification:
    notification = ChannelNotification.objects.create(
        tenant=tenant,
        session=session,
        nf_issue=nf_issue,
        phone_e164=phone_e164,
        event_type=event_type,
        message_body=message_body,
    )
    gateway = get_evolution_gateway()
    result = gateway.send_text(phone_e164=phone_e164, text=message_body)
    notification.provider_ref = result.get("ref", "")
    notification.status = (
        ChannelNotification.Status.SENT
        if result.get("ok")
        else ChannelNotification.Status.FAILED
    )
    notification.save(update_fields=["provider_ref", "status", "updated_at"])
    return notification
