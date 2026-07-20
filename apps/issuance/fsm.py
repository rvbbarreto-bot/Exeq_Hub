from apps.issuance.exceptions import InvalidTransitionError
from apps.issuance.models import NfIssue, NfIssueEvent

ALLOWED: dict[str, set[str]] = {
    NfIssue.Status.DRAFT: {NfIssue.Status.PENDING_TAX},
    NfIssue.Status.PENDING_TAX: {
        NfIssue.Status.QUEUED,
        NfIssue.Status.REJECTED,
    },
    NfIssue.Status.QUEUED: {
        NfIssue.Status.SUBMITTING,
        NfIssue.Status.FAILED,
    },
    NfIssue.Status.SUBMITTING: {
        NfIssue.Status.POLLING,
        NfIssue.Status.REJECTED,
        NfIssue.Status.FAILED,
    },
    NfIssue.Status.POLLING: {
        NfIssue.Status.AUTHORIZED,
        NfIssue.Status.REJECTED,
        NfIssue.Status.FAILED,
    },
    NfIssue.Status.AUTHORIZED: {NfIssue.Status.CANCELLED},
    NfIssue.Status.REJECTED: {NfIssue.Status.PENDING_TAX},
    NfIssue.Status.FAILED: {NfIssue.Status.PENDING_TAX},
    NfIssue.Status.CANCELLED: set(),
}


def transition(
    issue: NfIssue,
    *,
    to_status: str,
    actor: str,
    metadata: dict | None = None,
) -> NfIssue:
    allowed = ALLOWED.get(issue.status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(
            f"Transição inválida: {issue.status} -> {to_status}"
        )
    from_status = issue.status
    issue.status = to_status
    issue.save(update_fields=["status", "updated_at"])
    NfIssueEvent.objects.create(
        tenant_id=issue.tenant_id,
        nf_issue=issue,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        metadata=metadata,
    )
    return issue
