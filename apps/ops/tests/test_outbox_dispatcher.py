import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage


@pytest.mark.django_db
def test_outbox_authorized_notifies_when_phone_configured(tenant_a):
    tenant_a.settings = {"notify_phone": "+5511999999999"}
    tenant_a.save(update_fields=["settings"])

    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nf_issue.authorized",
        aggregate_type="nf_issue",
        aggregate_id=tenant_a.id,
        payload={"focus_ref": "FOCUS-ABC"},
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    msg.refresh_from_db()
    assert msg.status == OutboxMessage.Status.PROCESSED
    note = ChannelNotification.objects.get(tenant=tenant_a, event_type="nf_issue.authorized")
    assert note.status == ChannelNotification.Status.SENT
    assert "FOCUS-ABC" in note.message_body


@pytest.mark.django_db
def test_outbox_authorized_noop_without_phone(tenant_a):
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nf_issue.authorized",
        aggregate_type="nf_issue",
        aggregate_id=tenant_a.id,
        payload={"focus_ref": "FOCUS-X"},
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    assert ChannelNotification.objects.filter(tenant=tenant_a).count() == 0


@pytest.mark.django_db
def test_outbox_queued_skipped_by_dispatcher(tenant_a):
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nf_issue.queued",
        aggregate_type="nf_issue",
        aggregate_id=tenant_a.id,
        payload={},
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "skipped"
    msg.refresh_from_db()
    assert msg.status == OutboxMessage.Status.PROCESSED
