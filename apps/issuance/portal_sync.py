"""Sincronização assíncrona de status NFS-e com o portal nacional (SEFIN)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.issuance.models import NfIssue
from apps.issuance.polling import poll_nf_issue_status

logger = logging.getLogger(__name__)


def is_sefin_chave(ref: str) -> bool:
    digits = "".join(ch for ch in (ref or "") if ch.isdigit())
    return len(digits) == 50


def portal_sync_enabled() -> bool:
    if not getattr(settings, "NFSE_PORTAL_SYNC_ENABLED", True):
        return False
    mode = (getattr(settings, "SEFIN_HTTP_MODE", "stub") or "stub").lower()
    return mode == "http"


def min_sync_interval_seconds(*, force: bool = False) -> int:
    if force:
        return int(
            getattr(settings, "NFSE_PORTAL_SYNC_FORCE_INTERVAL_SECONDS", 30) or 30
        )
    return int(getattr(settings, "NFSE_PORTAL_SYNC_MIN_INTERVAL_SECONDS", 300) or 300)


def list_sync_limit() -> int:
    return int(getattr(settings, "NFSE_PORTAL_SYNC_LIST_LIMIT", 15) or 15)


def should_sync_issue(issue: NfIssue, *, force: bool = False) -> bool:
    if issue.status not in {NfIssue.Status.AUTHORIZED, NfIssue.Status.POLLING}:
        return False
    if not is_sefin_chave(issue.focus_ref or ""):
        return False
    if force:
        return True
    raw = issue.focus_status_raw or {}
    last = raw.get("portal_sync_at")
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(str(last))
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, timezone.get_current_timezone())
    except (TypeError, ValueError):
        return True
    return timezone.now() - ts >= timedelta(seconds=min_sync_interval_seconds(force=force))


def refresh_nf_issue_from_portal(issue: NfIssue) -> NfIssue:
    """Consulta SEFIN e aplica FSM (authorized → cancelled, polling → …)."""
    poll_nf_issue_status(issue)
    issue.refresh_from_db()
    raw = dict(issue.focus_status_raw or {})
    raw["portal_sync_at"] = timezone.now().isoformat(timespec="seconds")
    issue.focus_status_raw = raw
    issue.save(update_fields=["focus_status_raw", "updated_at"])
    return issue


def refresh_nf_issue_from_portal_by_id(
    *, tenant_id, issue_id: str, force: bool = False
) -> None:
    issue = (
        NfIssue.objects.select_related("tenant", "provider")
        .filter(tenant_id=tenant_id, id=issue_id)
        .first()
    )
    if issue is None or not should_sync_issue(issue, force=force):
        return
    try:
        refresh_nf_issue_from_portal(issue)
    except Exception:
        logger.exception(
            "portal_sync failed tenant=%s issue=%s",
            tenant_id,
            issue_id,
        )


def refresh_nfse_portal_status_batch(
    *, tenant_id, issue_ids: list[str], force: bool = False
) -> dict:
    processed = 0
    for issue_id in issue_ids:
        refresh_nf_issue_from_portal_by_id(
            tenant_id=tenant_id, issue_id=issue_id, force=force
        )
        processed += 1
    logger.info(
        "portal_sync batch done tenant=%s processed=%s ids=%s",
        tenant_id,
        processed,
        len(issue_ids),
    )
    return {"processed": processed}


def collect_issue_ids_for_portal_sync(issues, *, force: bool = False) -> list[str]:
    limit = list_sync_limit()
    ids: list[str] = []
    for issue in issues:
        if len(ids) >= limit:
            break
        if should_sync_issue(issue, force=force):
            ids.append(str(issue.id))
    return ids


def schedule_portal_status_refresh(
    *,
    tenant_id,
    issue_ids: list[str],
    force: bool = False,
) -> bool:
    """Dispara sync em background — nunca bloqueia o request HTTP."""
    if not portal_sync_enabled() or not issue_ids:
        return False

    ids = [str(i) for i in issue_ids if i]

    def _run_batch() -> None:
        try:
            refresh_nfse_portal_status_batch(
                tenant_id=str(tenant_id),
                issue_ids=ids,
                force=force,
            )
        except Exception:
            logger.exception("portal_sync batch failed tenant=%s", tenant_id)

    threading.Thread(
        target=_run_batch, daemon=True, name="nfse-portal-sync"
    ).start()
    return True
