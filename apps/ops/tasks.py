from celery import shared_task
from django.utils import timezone

from apps.ops.dispatcher import SKIP_EVENT_TYPES, claim_and_dispatch
from apps.ops.models import OutboxMessage
from shared.rls import tenant_rls


@shared_task(name="ops.dispatch_outbox_message")
def dispatch_outbox_message(message_id: str) -> str:
    msg = OutboxMessage.objects.filter(id=message_id).only("tenant_id").first()
    if msg is None:
        return "missing"
    with tenant_rls(str(msg.tenant_id)):
        return claim_and_dispatch(message_id)


@shared_task(name="ops.dispatch_pending_outbox")
def dispatch_pending_outbox(limit: int = 50) -> int:
    ids = list(
        OutboxMessage.objects.filter(
            status__in=[OutboxMessage.Status.PENDING, OutboxMessage.Status.FAILED],
            available_at__lte=timezone.now(),
        )
        .exclude(event_type__in=SKIP_EVENT_TYPES)
        .order_by("available_at")
        .values_list("id", flat=True)[:limit]
    )
    for message_id in ids:
        dispatch_outbox_message.delay(str(message_id))
    return len(ids)
