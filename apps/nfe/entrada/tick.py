"""Seleção de cursors elegíveis para sync automático (beat)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.nfe.entrada.feature import nfe_entrada_enabled_for_tenant, nfe_entrada_global_enabled
from apps.nfe.entrada.models import NfeDistribuicaoCursor


def list_distribuicao_due_cursors(*, limit: int = 50) -> list[NfeDistribuicaoCursor]:
    """Cursors com consulta automática e intervalo respeitado."""
    if not nfe_entrada_global_enabled():
        return []

    now = timezone.now()
    batch = max(1, int(limit or 50))
    qs = (
        NfeDistribuicaoCursor.objects.filter(automatic_enabled=True)
        .select_related("tenant", "provider")
        .order_by("last_query_at", "created_at")[: batch * 3]
    )

    due: list[NfeDistribuicaoCursor] = []
    for cursor in qs:
        if len(due) >= batch:
            break
        if not nfe_entrada_enabled_for_tenant(cursor.tenant):
            continue
        if cursor.blocked_until and cursor.blocked_until > now:
            continue
        if cursor.last_query_at is not None:
            interval = max(60, int(cursor.interval_seconds or 3600))
            if now < cursor.last_query_at + timedelta(seconds=interval):
                continue
        due.append(cursor)
    return due


def run_distribuicao_tick(*, limit: int = 50) -> dict:
    """Enfileira sync por cursor elegível."""
    from apps.nfe.entrada.tasks import distribuicao_sync_task

    due = list_distribuicao_due_cursors(limit=limit)
    enqueued = 0
    for cursor in due:
        distribuicao_sync_task.delay(str(cursor.tenant_id), str(cursor.provider_id))
        enqueued += 1
    return {"enqueued": enqueued, "due": len(due)}
