"""Jobs periódicos de cobrança (rede de segurança pós-webhook)."""

from __future__ import annotations

from celery import shared_task

from apps.billing.models import Charge
from apps.billing.services import sync_charge_from_gateway
from apps.billing.exceptions import ChargeNotFoundError, GatewayRegistrationError


def sync_open_charges(*, limit: int = 100) -> dict:
    """
    Sincroniza cobranças abertas com gateway_ref (batch).

    Cobre pending/registered/overdue — webhook é caminho principal; este job é fallback.
    """
    limit = max(1, min(int(limit or 100), 500))
    qs = (
        Charge.objects.filter(
            status__in=[
                Charge.Status.PENDING,
                Charge.Status.REGISTERED,
                Charge.Status.OVERDUE,
            ],
        )
        .exclude(gateway_ref="")
        .order_by("updated_at")[:limit]
    )
    ok = 0
    errors = 0
    for charge in qs:
        try:
            sync_charge_from_gateway(charge)
            ok += 1
        except (ChargeNotFoundError, GatewayRegistrationError):
            errors += 1
        except Exception:  # noqa: BLE001 — batch não deve abortar
            errors += 1
    return {"synced": ok, "errors": errors, "limit": limit}


@shared_task(name="billing.sync_open_charges")
def sync_open_charges_task(limit: int = 100) -> dict:
    return sync_open_charges(limit=limit)
