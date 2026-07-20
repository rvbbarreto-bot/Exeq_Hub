from django.db import transaction
from django.utils import timezone

from apps.ops.dispatcher import SKIP_EVENT_TYPES
from apps.ops.models import OutboxMessage


def enqueue_outbox(
    *,
    tenant,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    payload: dict | None = None,
    correlation_id=None,
) -> OutboxMessage:
    msg = OutboxMessage.objects.create(
        tenant=tenant,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        available_at=timezone.now(),
        correlation_id=correlation_id,
    )
    if event_type not in SKIP_EVENT_TYPES:
        message_id = str(msg.id)

        def _schedule() -> None:
            from apps.ops.tasks import dispatch_outbox_message

            dispatch_outbox_message.delay(message_id)

        transaction.on_commit(_schedule)
    return msg
