"""Reservação de nNF (D-06) — lock de linha + retry (race create / lock SQLite)."""

from __future__ import annotations

import time

from django.db import IntegrityError, transaction
from django.db.utils import OperationalError

from apps.nfe.models import NfeNumberSeries

_MAX_ATTEMPTS = 20
_BACKOFF_BASE = 0.01


def _get_active_series_for_update(
    *,
    tenant_id,
    provider_id,
    series: int,
    tp_amb: str,
) -> NfeNumberSeries | None:
    return (
        NfeNumberSeries.objects.select_for_update()
        .filter(
            tenant_id=tenant_id,
            provider_id=provider_id,
            series=series,
            tp_amb=tp_amb,
            is_active=True,
        )
        .first()
    )


@transaction.atomic
def _reserve_once(
    *,
    tenant_id,
    provider_id,
    series: int,
    tp_amb: str,
) -> int:
    row = _get_active_series_for_update(
        tenant_id=tenant_id,
        provider_id=provider_id,
        series=series,
        tp_amb=tp_amb,
    )
    if row is None:
        try:
            with transaction.atomic():
                NfeNumberSeries.objects.create(
                    tenant_id=tenant_id,
                    provider_id=provider_id,
                    series=series,
                    tp_amb=tp_amb,
                    next_number=1,
                    is_active=True,
                )
        except IntegrityError:
            pass
        row = _get_active_series_for_update(
            tenant_id=tenant_id,
            provider_id=provider_id,
            series=series,
            tp_amb=tp_amb,
        )
        if row is None:
            raise RuntimeError(
                "não foi possível obter série NF-e para reserva (provider/série/ambiente)"
            )

    n = int(row.next_number)
    row.next_number = n + 1
    row.save(update_fields=["next_number", "updated_at"])
    return n


def reserve_next_number(
    *,
    tenant_id,
    provider_id,
    series: int,
    tp_amb: str,
) -> int:
    """
    Reserva nNF com lock de linha (D-06 / DoD domínio #4).

    - Postgres: `select_for_update` serializa contadores.
    - SQLite lab: retries em `database is locked` (threads concorrentes).
    - Create concorrente: `IntegrityError` → re-read com lock.
    """
    last_exc: BaseException | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return _reserve_once(
                tenant_id=tenant_id,
                provider_id=provider_id,
                series=series,
                tp_amb=tp_amb,
            )
        except (OperationalError, IntegrityError) as exc:
            last_exc = exc
            time.sleep(_BACKOFF_BASE * (attempt + 1))
    assert last_exc is not None
    raise last_exc
