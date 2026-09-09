"""Celery — sync NF-e entrada (distNSU)."""

from __future__ import annotations

import logging
import uuid

from celery import shared_task

from apps.accounts.models import Tenant
from apps.master_data.models import Provider
from apps.nfe.entrada.exceptions import DistributionError, NfeEntradaDisabledError
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from shared.rls import tenant_rls

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="nfe.distribuicao_sync",
    max_retries=3,
    default_retry_delay=60,
)
def distribuicao_sync_task(
    self,
    tenant_id: str,
    provider_id: str,
    correlation_id: str | None = None,
) -> dict:
    """Consulta distNSU para (tenant, provider)."""
    corr = uuid.UUID(correlation_id) if correlation_id else None
    with tenant_rls(tenant_id):
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        provider = Provider.objects.filter(pk=provider_id, tenant_id=tenant_id).first()
        if tenant is None or provider is None:
            logger.warning(
                "nfe.distribuicao_sync missing tenant=%s provider=%s",
                tenant_id,
                provider_id,
            )
            return {"ok": False, "reason": "not_found"}

        try:
            result = sync_distribuicao_once(
                tenant=tenant,
                provider=provider,
                actor="worker",
                correlation_id=corr,
            )
        except NfeEntradaDisabledError:
            return {"ok": False, "reason": "disabled"}
        except DistributionError as exc:
            logger.warning(
                "nfe.distribuicao_sync distribution_error tenant=%s provider=%s err=%s",
                tenant_id,
                provider_id,
                exc,
            )
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc, countdown=60 * (2**self.request.retries)) from exc
            return {"ok": False, "reason": "distribution_error", "message": str(exc)}

    payload = {
        "ok": result.success,
        "skipped": result.skipped,
        "blocked": result.blocked,
        "c_stat": result.c_stat,
        "documents_created": result.documents_created,
        "documents_processed": result.documents_processed,
        "ult_nsu_after": result.ult_nsu_after,
        "correlation_id": str(result.correlation_id),
    }
    logger.info(
        "nfe.distribuicao_sync tenant=%s provider=%s cStat=%s created=%s skipped=%s",
        tenant_id,
        provider_id,
        result.c_stat,
        result.documents_created,
        result.skipped,
    )
    return payload


@shared_task(name="nfe.distribuicao_tick")
def distribuicao_tick_task(limit: int = 50) -> dict:
    """Beat — enfileira sync para cursors automáticos elegíveis."""
    from apps.nfe.entrada.tick import run_distribuicao_tick

    result = run_distribuicao_tick(limit=limit)
    logger.info("nfe.distribuicao_tick %s", result)
    return result
