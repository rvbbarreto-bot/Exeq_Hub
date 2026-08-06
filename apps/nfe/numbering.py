from __future__ import annotations

from django.db import transaction

from apps.nfe.models import NfeNumberSeries


@transaction.atomic
def reserve_next_number(
    *,
    tenant_id,
    provider_id,
    series: int,
    tp_amb: str,
) -> int:
    """Reserva nNF com lock de linha (D-06)."""
    row = (
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
    if row is None:
        row = NfeNumberSeries.objects.create(
            tenant_id=tenant_id,
            provider_id=provider_id,
            series=series,
            tp_amb=tp_amb,
            next_number=1,
            is_active=True,
        )
        row = NfeNumberSeries.objects.select_for_update().get(pk=row.pk)
    n = row.next_number
    row.next_number = n + 1
    row.save(update_fields=["next_number", "updated_at"])
    return n
