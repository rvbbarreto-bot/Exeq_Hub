from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.models import WebhookInbox
from apps.issuance.exceptions import InvalidTransitionError
from apps.issuance.fsm import transition
from apps.issuance.models import NfIssue
from apps.ops.services import enqueue_outbox
from integrations.nfse.focus import AUTHORIZED, CANCELLED
from shared.exceptions import DomainError

REJECTED = frozenset(
    {
        "erro_autorizacao",
        "denied",
        "rejected",
        "erro",
    }
)


class InvalidFocusWebhookAuthError(DomainError):
    code = "FOCUS_WEBHOOK_AUTH"


class FocusNfseWebhookNotFoundError(DomainError):
    code = "FOCUS_NFSE_REF_NOT_FOUND"


def _advance_to_polling(issue: NfIssue) -> NfIssue:
    if issue.status == NfIssue.Status.QUEUED:
        transition(issue, to_status=NfIssue.Status.SUBMITTING, actor="provider")
    if issue.status == NfIssue.Status.SUBMITTING:
        transition(issue, to_status=NfIssue.Status.POLLING, actor="provider")
    return issue


@transaction.atomic
def ingest_focus_nfse_webhook(
    *,
    raw_authorization: str,
    payload: dict,
) -> WebhookInbox:
    expected = getattr(settings, "FOCUS_WEBHOOK_SECRET", "") or ""
    if expected and raw_authorization != expected:
        raise InvalidFocusWebhookAuthError("Assinatura Focus inválida")

    ref = str(payload.get("ref") or "").strip()
    if not ref:
        raise FocusNfseWebhookNotFoundError("ref ausente no webhook Focus")

    issue = (
        NfIssue.objects.select_for_update()
        .select_related("tenant")
        .filter(focus_ref=ref)
        .first()
    )
    if issue is None:
        issue = (
            NfIssue.objects.select_for_update()
            .select_related("tenant")
            .filter(id=ref)
            .first()
        )
    if issue is None:
        raise FocusNfseWebhookNotFoundError(f"NfIssue não encontrada para ref={ref}")

    status_raw = str(payload.get("status") or "").lower()
    idempotency_key = f"focus:{ref}:{status_raw}:{WebhookInbox.hash_payload(payload)[:16]}"
    inbox, _ = WebhookInbox.objects.get_or_create(
        tenant=issue.tenant,
        provider="focus",
        idempotency_key=idempotency_key,
        defaults={
            "signature": (raw_authorization or "")[:256],
            "signature_valid": True,
            "raw_payload": payload,
            "payload_hash": WebhookInbox.hash_payload(payload),
            "status": WebhookInbox.Status.RECEIVED,
        },
    )
    if inbox.status == WebhookInbox.Status.PROCESSED:
        return inbox

    inbox.status = WebhookInbox.Status.PROCESSING
    inbox.save(update_fields=["status", "updated_at"])

    issue.focus_status_raw = payload
    if not issue.focus_ref:
        issue.focus_ref = ref
    issue.save(update_fields=["focus_status_raw", "focus_ref", "updated_at"])

    try:
        _apply_provider_status(issue, status_raw=status_raw)
    except InvalidTransitionError as exc:
        inbox.status = WebhookInbox.Status.FAILED
        inbox.error_message = str(exc)[:500]
        inbox.save(update_fields=["status", "error_message", "updated_at"])
        raise

    inbox.status = WebhookInbox.Status.PROCESSED
    inbox.processed_at = timezone.now()
    inbox.error_message = ""
    inbox.save(update_fields=["status", "processed_at", "error_message", "updated_at"])
    return inbox


def _apply_provider_status(issue: NfIssue, *, status_raw: str) -> None:
    if status_raw in CANCELLED:
        if issue.status == NfIssue.Status.CANCELLED:
            return
        if issue.status == NfIssue.Status.AUTHORIZED:
            transition(
                issue,
                to_status=NfIssue.Status.CANCELLED,
                actor="provider",
                metadata={"focus_ref": issue.focus_ref, "via": "webhook"},
            )
            enqueue_outbox(
                tenant=issue.tenant,
                event_type="nf_issue.cancelled",
                aggregate_type="nf_issue",
                aggregate_id=issue.id,
                payload={
                    "nf_issue_id": str(issue.id),
                    "focus_ref": issue.focus_ref,
                },
                correlation_id=issue.correlation_id,
            )
            return
        # Emissão ainda não autorizada: trata cancelamento prematuro como rejeição
        issue.rejection_code = status_raw.upper()
        issue.save(update_fields=["rejection_code", "updated_at"])
        _advance_to_polling(issue)
        if issue.status == NfIssue.Status.POLLING:
            transition(
                issue,
                to_status=NfIssue.Status.REJECTED,
                actor="provider",
                metadata={"status": status_raw, "via": "webhook"},
            )
        return

    if status_raw in AUTHORIZED or status_raw == "authorized":
        if issue.status == NfIssue.Status.AUTHORIZED:
            return
        _advance_to_polling(issue)
        if issue.status == NfIssue.Status.POLLING:
            transition(
                issue,
                to_status=NfIssue.Status.AUTHORIZED,
                actor="provider",
                metadata={"focus_ref": issue.focus_ref, "via": "webhook"},
            )
            enqueue_outbox(
                tenant=issue.tenant,
                event_type="nf_issue.authorized",
                aggregate_type="nf_issue",
                aggregate_id=issue.id,
                payload={
                    "nf_issue_id": str(issue.id),
                    "focus_ref": issue.focus_ref,
                },
                correlation_id=issue.correlation_id,
            )
            from apps.issuance.artifacts import ensure_authorized_artifacts

            ensure_authorized_artifacts(issue)
        return

    if status_raw in REJECTED:
        if issue.status == NfIssue.Status.REJECTED:
            return
        issue.rejection_code = status_raw.upper()
        issue.save(update_fields=["rejection_code", "updated_at"])
        _advance_to_polling(issue)
        if issue.status == NfIssue.Status.POLLING:
            transition(
                issue,
                to_status=NfIssue.Status.REJECTED,
                actor="provider",
                metadata={"status": status_raw, "via": "webhook"},
            )
