from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.issuance.models import NfIssue
from apps.issuance.polling import poll_nf_issue_status
from apps.issuance.services import process_queued_issue
from apps.ops.models import OutboxMessage
from shared.rls import tenant_rls


@shared_task(name="issuance.process_nf_issue")
def process_nf_issue(tenant_id: str, nf_issue_id: str) -> str:
    with tenant_rls(tenant_id):
        with transaction.atomic():
            issue = NfIssue.objects.select_for_update().get(
                tenant_id=tenant_id,
                id=nf_issue_id,
            )
            OutboxMessage.objects.filter(
                tenant_id=tenant_id,
                aggregate_id=nf_issue_id,
                event_type="nf_issue.queued",
                status=OutboxMessage.Status.PENDING,
            ).update(status=OutboxMessage.Status.PROCESSING)
            process_queued_issue(issue)
            OutboxMessage.objects.filter(
                tenant_id=tenant_id,
                aggregate_id=nf_issue_id,
                event_type="nf_issue.queued",
                status=OutboxMessage.Status.PROCESSING,
            ).update(status=OutboxMessage.Status.PROCESSED)
    return str(nf_issue_id)


@shared_task(
    bind=True,
    name="issuance.poll_nf_issue",
    max_retries=12,
    default_retry_delay=30,
)
def poll_nf_issue_task(self, tenant_id: str, nf_issue_id: str) -> str:
    with tenant_rls(tenant_id):
        with transaction.atomic():
            issue = NfIssue.objects.select_for_update().get(
                tenant_id=tenant_id,
                id=nf_issue_id,
            )
            poll_nf_issue_status(issue)
            issue.refresh_from_db()
            if issue.status != NfIssue.Status.POLLING:
                return str(nf_issue_id)

    countdown = int(getattr(settings, "FOCUS_POLL_COUNTDOWN", 15) or 15)
    backoff = min(countdown * (2 ** self.request.retries), 300)
    raise self.retry(countdown=backoff)
