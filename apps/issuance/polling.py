from django.conf import settings
from django.db import transaction

from apps.issuance.fsm import transition
from apps.issuance.models import NfIssue
from apps.ops.services import enqueue_outbox
from integrations.nfse.factory import get_nfse_provider
from integrations.nfse.focus import AUTHORIZED, CANCELLED

REJECTED = frozenset(
    {
        "erro_autorizacao",
        "denied",
        "rejected",
        "erro",
    }
)


@transaction.atomic
def poll_nf_issue_status(issue: NfIssue) -> NfIssue:
    """Consulta provedor enquanto a nota está em polling ou após cancelamento pendente."""
    if issue.status not in {NfIssue.Status.POLLING, NfIssue.Status.AUTHORIZED}:
        return issue
    if not issue.focus_ref:
        if issue.status == NfIssue.Status.POLLING:
            transition(
                issue,
                to_status=NfIssue.Status.FAILED,
                actor="worker",
                metadata={"reason": "missing_focus_ref"},
            )
        return issue

    provider = get_nfse_provider(
        ibge_code=issue.ibge_code,
        tenant_settings=issue.tenant.settings or {},
        tenant=issue.tenant,
        tax_regime=issue.provider.tax_regime,
        competence_date=issue.competence_date,
    )
    result = provider.consultar(ref=issue.focus_ref)
    issue.focus_status_raw = result.raw
    issue.save(update_fields=["focus_status_raw", "updated_at"])

    status = (result.status or "").lower()
    raw_status = str((result.raw or {}).get("status") or status).lower()

    if issue.status == NfIssue.Status.AUTHORIZED and (
        status in CANCELLED or raw_status in CANCELLED
    ):
        transition(
            issue,
            to_status=NfIssue.Status.CANCELLED,
            actor="provider",
            metadata={"focus_ref": issue.focus_ref, "via": "poll"},
        )
        enqueue_outbox(
            tenant=issue.tenant,
            event_type="nf_issue.cancelled",
            aggregate_type="nf_issue",
            aggregate_id=issue.id,
            payload={"nf_issue_id": str(issue.id), "focus_ref": issue.focus_ref},
            correlation_id=issue.correlation_id,
        )
        return issue

    if issue.status != NfIssue.Status.POLLING:
        return issue

    if status == "authorized" or status in AUTHORIZED or raw_status in AUTHORIZED:
        transition(
            issue,
            to_status=NfIssue.Status.AUTHORIZED,
            actor="provider",
            metadata={"focus_ref": issue.focus_ref, "provider": provider.kind},
        )
        enqueue_outbox(
            tenant=issue.tenant,
            event_type="nf_issue.authorized",
            aggregate_type="nf_issue",
            aggregate_id=issue.id,
            payload={"nf_issue_id": str(issue.id), "focus_ref": issue.focus_ref},
            correlation_id=issue.correlation_id,
        )
        from apps.issuance.artifacts import ensure_authorized_artifacts

        ensure_authorized_artifacts(issue)
        return issue

    if status in REJECTED or raw_status in REJECTED or raw_status in CANCELLED:
        issue.rejection_code = (raw_status or status).upper()
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.REJECTED,
            actor="provider",
            metadata={"status": raw_status or status},
        )
        return issue

    return issue


def schedule_poll(issue: NfIssue) -> None:
    from apps.issuance.tasks import poll_nf_issue_task

    countdown = int(getattr(settings, "FOCUS_POLL_COUNTDOWN", 15) or 15)
    if settings.CELERY_TASK_ALWAYS_EAGER or settings.NF_SYNC_PROCESSING:
        poll_nf_issue_status(issue)
        issue.refresh_from_db()
        return
    poll_nf_issue_task.apply_async(
        args=[str(issue.tenant_id), str(issue.id)],
        countdown=countdown,
    )
