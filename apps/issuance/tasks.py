import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction

from apps.issuance.fsm import transition
from apps.issuance.models import NfIssue
from apps.issuance.polling import poll_nf_issue_status
from apps.issuance.services import process_queued_issue
from apps.ops.models import OutboxMessage
from integrations.nfse.resilience import resolve_poll_time_limits, resolve_process_time_limits
from shared.rls import tenant_rls

logger = logging.getLogger(__name__)

_PROCESS_SOFT, _PROCESS_HARD = resolve_process_time_limits()
_POLL_SOFT, _POLL_HARD = resolve_poll_time_limits()


def _mark_failed_on_soft_limit(tenant_id: str, nf_issue_id: str) -> None:
    """Best-effort: não deixar nota em submitting/queued após corte de tempo."""
    try:
        with tenant_rls(tenant_id):
            with transaction.atomic():
                issue = (
                    NfIssue.objects.select_for_update()
                    .filter(tenant_id=tenant_id, id=nf_issue_id)
                    .first()
                )
                if issue is None:
                    return
                if issue.status not in {
                    NfIssue.Status.QUEUED,
                    NfIssue.Status.SUBMITTING,
                    NfIssue.Status.POLLING,
                }:
                    return
                issue.focus_status_raw = {
                    **(issue.focus_status_raw or {}),
                    "error": "Celery soft_time_limit (SEC-P2-04)",
                }
                issue.rejection_code = "SEFIN_TIMEOUT_BUDGET"
                issue.save(
                    update_fields=[
                        "focus_status_raw",
                        "rejection_code",
                        "updated_at",
                    ]
                )
                if issue.status != NfIssue.Status.FAILED:
                    transition(
                        issue,
                        to_status=NfIssue.Status.FAILED,
                        actor="worker",
                        metadata={"ex": "EX-NET", "sec": "P2-04"},
                    )
                OutboxMessage.objects.filter(
                    tenant_id=tenant_id,
                    aggregate_id=nf_issue_id,
                    event_type="nf_issue.queued",
                    status=OutboxMessage.Status.PROCESSING,
                ).update(status=OutboxMessage.Status.FAILED)
    except Exception:  # noqa: BLE001
        logger.exception(
            "nfse.soft_limit mark_failed failed issue=%s",
            nf_issue_id,
        )


@shared_task(
    name="issuance.process_nf_issue",
    soft_time_limit=_PROCESS_SOFT,
    time_limit=_PROCESS_HARD,
)
def process_nf_issue(tenant_id: str, nf_issue_id: str) -> str:
    try:
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
    except SoftTimeLimitExceeded:
        logger.error(
            "nfse.process soft_time_limit issue=%s soft=%s hard=%s",
            nf_issue_id,
            _PROCESS_SOFT,
            _PROCESS_HARD,
        )
        _mark_failed_on_soft_limit(tenant_id, nf_issue_id)
        raise


@shared_task(
    bind=True,
    name="issuance.poll_nf_issue",
    max_retries=12,
    default_retry_delay=30,
    soft_time_limit=_POLL_SOFT,
    time_limit=_POLL_HARD,
)
def poll_nf_issue_task(self, tenant_id: str, nf_issue_id: str) -> str:
    try:
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
    except SoftTimeLimitExceeded:
        logger.error(
            "nfse.poll soft_time_limit issue=%s soft=%s",
            nf_issue_id,
            _POLL_SOFT,
        )
        _mark_failed_on_soft_limit(tenant_id, nf_issue_id)
        raise
