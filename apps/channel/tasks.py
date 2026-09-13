import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.channel.models import ChannelSession

logger = logging.getLogger(__name__)


@shared_task(name="channel.expire_stale_sessions")
def expire_stale_sessions() -> int:
    """WA-FLX-07 — expira sessões de conversa paradas além do TTL."""
    cutoff = timezone.now() - timedelta(
        minutes=int(getattr(settings, "CHANNEL_SESSION_TTL_MINUTES", 30))
    )
    updated = ChannelSession.objects.filter(
        status__in=[
            ChannelSession.Status.COLLECTING,
            ChannelSession.Status.READY_TO_CONFIRM,
        ],
        last_message_at__lt=cutoff,
    ).update(status=ChannelSession.Status.EXPIRED)
    if updated:
        logger.info("channel.expire_stale_sessions expired=%s", updated)
    return updated
