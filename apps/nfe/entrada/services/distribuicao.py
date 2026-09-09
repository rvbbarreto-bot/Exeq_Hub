"""Serviço de distribuição DFe — distNSU transacional."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.master_data.models import Provider
from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.exceptions import DistributionError, NfeEntradaDisabledError
from apps.nfe.entrada.feature import require_nfe_entrada_enabled
from apps.nfe.entrada.models import NfeDistribuicaoCursor, NfeDistribuicaoSyncLog
from apps.nfe.entrada.services.document import upsert_entrada_document
from integrations.sefaz_nfe.distribuicao import (
    CSTAT_CONSUMO_INDEVIDO,
    CSTAT_DOCUMENTOS_LOCALIZADOS,
    CSTAT_NENHUM_DOCUMENTO,
    get_nfe_distribuicao_provider,
)
from integrations.sefaz_nfe.distribuicao.parse import DocumentParseError, parse_distribuicao_xml
from integrations.sefaz_nfe.distribuicao.port import NfeDistribuicaoResult, _pad_nsu

logger = logging.getLogger(__name__)

_SUCCESS_CSTATS = frozenset({CSTAT_NENHUM_DOCUMENTO, CSTAT_DOCUMENTOS_LOCALIZADOS})


@dataclass
class SyncResult:
    success: bool
    c_stat: str = ""
    x_motivo: str = ""
    documents_processed: int = 0
    documents_created: int = 0
    ult_nsu_before: str = "0"
    ult_nsu_after: str = "0"
    blocked: bool = False
    skipped: bool = False
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class _FetchState:
    batches: list[NfeDistribuicaoResult]
    ult_nsu_work: str
    total_processed: int = 0
    total_created: int = 0


def _nsu_int(value: str) -> int:
    return int("".join(c for c in str(value or "0") if c.isdigit()) or "0")


def _process_lote(
    *,
    tenant: Tenant,
    provider: Provider,
    documents: tuple,
) -> tuple[int, int]:
    processed = 0
    created = 0
    for item in documents:
        parsed = parse_distribuicao_xml(nsu=item.nsu, xml_bytes=item.xml_bytes)
        result = upsert_entrada_document(tenant=tenant, provider=provider, parsed=parsed)
        processed += 1
        if result.created:
            created += 1
    return processed, created


def _highest_nsu_from_batch(dist: NfeDistribuicaoResult) -> str:
    new_ult = _pad_nsu(dist.max_nsu)
    for item in dist.documents:
        item_nsu = _pad_nsu(item.nsu)
        if _nsu_int(item_nsu) > _nsu_int(new_ult):
            new_ult = item_nsu
    return new_ult


def _fetch_dist_batches(
    *,
    tenant: Tenant,
    provider: Provider,
    cursor: NfeDistribuicaoCursor,
    stub_mode: str | None,
) -> _FetchState:
    """HTTP distNSU — fora de transação DB."""
    provider_api = get_nfe_distribuicao_provider()
    ctx: dict = {"tenant": tenant, "provider": provider}
    if stub_mode:
        ctx["stub_mode"] = stub_mode

    batches: list[NfeDistribuicaoResult] = []
    ult_work = cursor.ult_nsu

    while True:
        dist = provider_api.consultar_dist_nsu(
            cnpj=cursor.cnpj,
            ult_nsu=ult_work,
            tp_amb=cursor.tp_amb,
            context=ctx,
        )
        batches.append(dist)

        if dist.c_stat in (CSTAT_CONSUMO_INDEVIDO, CSTAT_NENHUM_DOCUMENTO):
            break

        if dist.c_stat != CSTAT_DOCUMENTOS_LOCALIZADOS:
            raise DistributionError(
                f"distNSU retornou cStat inesperado: {dist.c_stat} — {dist.x_motivo}"
            )
        if not dist.documents:
            raise DistributionError("cStat 138 sem documentos no lote")

        ult_work = _highest_nsu_from_batch(dist)
        max_nsu = _pad_nsu(dist.max_nsu or ult_work)
        if _nsu_int(ult_work) < _nsu_int(max_nsu):
            continue
        break

    return _FetchState(batches=batches, ult_nsu_work=ult_work)


def sync_distribuicao_once(
    *,
    tenant: Tenant,
    provider: Provider,
    actor: str = "worker",
    correlation_id: uuid.UUID | None = None,
    stub_mode: str | None = None,
) -> SyncResult:
    """
    Lock cursor (skip_locked) → distNSU HTTP → persiste docs + NSU em transação curta.
    """
    require_nfe_entrada_enabled(tenant=tenant)
    corr = correlation_id or uuid.uuid4()
    started = time.monotonic()
    result = SyncResult(success=False, correlation_id=corr)

    with transaction.atomic():
        cursor = get_or_create_cursor(tenant=tenant, provider=provider)
        cursor = (
            NfeDistribuicaoCursor.objects.select_for_update(skip_locked=True)
            .filter(pk=cursor.pk)
            .first()
        )
        if cursor is None:
            result.skipped = True
            result.x_motivo = "Cursor em sync por outro worker"
            return result

        now = timezone.now()
        if cursor.blocked_until and cursor.blocked_until > now:
            result.blocked = True
            result.c_stat = CSTAT_CONSUMO_INDEVIDO
            result.x_motivo = "Consulta bloqueada por consumo indevido anterior"
            result.ult_nsu_before = cursor.ult_nsu
            result.ult_nsu_after = cursor.ult_nsu
            _write_sync_log(
                cursor=cursor,
                result=result,
                actor=actor,
                started=started,
                error_message=result.x_motivo,
            )
            return result

        result.ult_nsu_before = cursor.ult_nsu
        cursor_pk = cursor.pk
        ult_before = cursor.ult_nsu
        cursor_snapshot = cursor

    fetch = _fetch_dist_batches(
        tenant=tenant,
        provider=provider,
        cursor=cursor_snapshot,
        stub_mode=stub_mode,
    )

    with transaction.atomic():
        cursor = NfeDistribuicaoCursor.objects.select_for_update().get(pk=cursor_pk)
        if cursor.ult_nsu != ult_before:
            result.skipped = True
            result.x_motivo = "NSU alterado por outra execução"
            result.ult_nsu_after = cursor.ult_nsu
            return result

        now = timezone.now()
        total_processed = 0
        total_created = 0
        last_c_stat = ""
        last_x_motivo = ""
        last_max_nsu = cursor.max_nsu

        for dist in fetch.batches:
            last_c_stat = dist.c_stat
            last_x_motivo = dist.x_motivo
            last_max_nsu = _pad_nsu(dist.max_nsu or cursor.max_nsu)

            if dist.c_stat == CSTAT_CONSUMO_INDEVIDO:
                block_seconds = int(getattr(settings, "NFE_ENTRADA_BLOCK_656_SECONDS", 3600) or 3600)
                cursor.blocked_until = now + timedelta(seconds=block_seconds)
                cursor.last_c_stat = dist.c_stat
                cursor.last_x_motivo = dist.x_motivo
                cursor.last_query_at = now
                cursor.save(
                    update_fields=[
                        "blocked_until",
                        "last_c_stat",
                        "last_x_motivo",
                        "last_query_at",
                        "updated_at",
                    ]
                )
                result.blocked = True
                result.c_stat = dist.c_stat
                result.x_motivo = dist.x_motivo
                result.ult_nsu_after = cursor.ult_nsu
                _write_sync_log(
                    cursor=cursor,
                    result=result,
                    actor=actor,
                    started=started,
                    max_nsu=last_max_nsu,
                    error_message=dist.x_motivo,
                )
                return result

            if dist.c_stat == CSTAT_NENHUM_DOCUMENTO:
                cursor.ult_nsu = _pad_nsu(dist.ult_nsu or cursor.ult_nsu)
                cursor.max_nsu = last_max_nsu
                cursor.last_c_stat = dist.c_stat
                cursor.last_x_motivo = dist.x_motivo
                cursor.last_query_at = now
                cursor.blocked_until = None
                cursor.save(
                    update_fields=[
                        "ult_nsu",
                        "max_nsu",
                        "last_c_stat",
                        "last_x_motivo",
                        "last_query_at",
                        "blocked_until",
                        "updated_at",
                    ]
                )
                result.success = True
                result.c_stat = dist.c_stat
                result.x_motivo = dist.x_motivo
                result.documents_processed = total_processed
                result.documents_created = total_created
                result.ult_nsu_after = cursor.ult_nsu
                _write_sync_log(
                    cursor=cursor,
                    result=result,
                    actor=actor,
                    started=started,
                    max_nsu=last_max_nsu,
                )
                return result

            batch_processed, batch_created = _process_lote(
                tenant=tenant,
                provider=provider,
                documents=dist.documents,
            )
            total_processed += batch_processed
            total_created += batch_created
            cursor.ult_nsu = _highest_nsu_from_batch(dist)

        cursor.max_nsu = last_max_nsu
        cursor.last_c_stat = last_c_stat
        cursor.last_x_motivo = last_x_motivo
        cursor.last_query_at = now
        cursor.blocked_until = None
        cursor.save(
            update_fields=[
                "ult_nsu",
                "max_nsu",
                "last_c_stat",
                "last_x_motivo",
                "last_query_at",
                "blocked_until",
                "updated_at",
            ]
        )

        result.success = True
        result.c_stat = last_c_stat
        result.x_motivo = last_x_motivo
        result.documents_processed = total_processed
        result.documents_created = total_created
        result.ult_nsu_after = cursor.ult_nsu
        _write_sync_log(
            cursor=cursor,
            result=result,
            actor=actor,
            started=started,
            max_nsu=last_max_nsu,
        )
        return result


def _write_sync_log(
    *,
    cursor: NfeDistribuicaoCursor,
    result: SyncResult,
    actor: str,
    started: float,
    max_nsu: str = "",
    error_message: str = "",
) -> None:
    duration_ms = int((time.monotonic() - started) * 1000)
    NfeDistribuicaoSyncLog.objects.create(
        tenant_id=cursor.tenant_id,
        provider_id=cursor.provider_id,
        cnpj=cursor.cnpj,
        ult_nsu_before=result.ult_nsu_before,
        ult_nsu_after=result.ult_nsu_after,
        max_nsu=max_nsu or cursor.max_nsu,
        c_stat=result.c_stat,
        x_motivo=result.x_motivo,
        documents_count=result.documents_processed,
        duration_ms=duration_ms,
        correlation_id=result.correlation_id,
        actor=actor,
        success=result.success and result.c_stat in _SUCCESS_CSTATS,
        error_message=error_message,
    )


def schedule_distribuicao_sync(
    *,
    tenant: Tenant,
    provider: Provider,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Enfileira sync (ou executa inline se CELERY_TASK_ALWAYS_EAGER)."""
    from apps.nfe.entrada.tasks import distribuicao_sync_task

    corr = correlation_id or uuid.uuid4()
    async_result = distribuicao_sync_task.delay(
        str(tenant.id),
        str(provider.id),
        str(corr),
    )
    return str(async_result.id)


__all__ = [
    "SyncResult",
    "sync_distribuicao_once",
    "schedule_distribuicao_sync",
    "DocumentParseError",
    "NfeEntradaDisabledError",
]
