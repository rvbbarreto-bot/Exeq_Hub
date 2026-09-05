"""Reservação nNF série mod 65."""

from __future__ import annotations

import time

from django.db import IntegrityError, transaction
from django.db.utils import OperationalError

from apps.nfce.models import NfceNumberSeries

_MAX_ATTEMPTS = 20
_BACKOFF_BASE = 0.01


def _get_active_series_for_update(
    *,
    tenant_id,
    provider_id,
    series: int,
    tp_amb: str,
) -> NfceNumberSeries | None:
    return (
        NfceNumberSeries.objects.select_for_update()
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
                NfceNumberSeries.objects.create(
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
                "não foi possível obter série NFC-e para reserva (provider/série/ambiente)"
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
