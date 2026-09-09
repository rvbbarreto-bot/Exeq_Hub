"""Sincroniza FoodOrder ↔ NFC-e (B5/B8)."""

from __future__ import annotations

import uuid

from apps.food.exceptions import FoodInvalidOrderError
from apps.food.fiscal.emit import map_invoice_to_food_fiscal_status
from apps.food.fiscal.readiness import refresh_food_order_fiscal_state
from apps.food.models import FoodFiscalEvent, FoodOrder
from apps.nfce.models import NfceInvoice
from apps.nfce.services import cancel_nfce


def _food_order_ids_for_invoice(invoice: NfceInvoice) -> set:
    ids: set = set(
        FoodOrder.objects.filter(
            nfce_invoice=invoice,
            channel=FoodOrder.Channel.IFOOD,
        ).values_list("pk", flat=True)
    )
    key = (invoice.idempotency_key or "").strip()
    prefix = "food:ifood:"
    if key.startswith(prefix):
        raw = key[len(prefix) :].split(":a", 1)[0]
        try:
            oid = uuid.UUID(raw)
            ids.add(oid)
        except ValueError:
            pass
    return ids


def sync_food_orders_from_nfce_invoice(invoice: NfceInvoice) -> int:
    """Propaga status NFC-e para pedidos iFood vinculados (EX-EMT-07)."""
    if invoice.status not in {
        NfceInvoice.Status.AUTHORIZED,
        NfceInvoice.Status.REJECTED,
        NfceInvoice.Status.FAILED,
        NfceInvoice.Status.CANCELLED,
        NfceInvoice.Status.POLLING,
        NfceInvoice.Status.SUBMITTING,
    }:
        return 0

    target_fs = map_invoice_to_food_fiscal_status(invoice)
    updated = 0
    for oid in _food_order_ids_for_invoice(invoice):
        order = (
            FoodOrder.objects.filter(
                pk=oid,
                tenant_id=invoice.tenant_id,
                channel=FoodOrder.Channel.IFOOD,
            )
            .select_related("nfce_invoice")
            .first()
        )
        if order is None:
            continue
        prev_fs = order.fiscal_status
        if (
            order.fiscal_status == target_fs
            and order.nfce_invoice_id == invoice.pk
            and target_fs != FoodOrder.FiscalStatus.REJECTED
        ):
            continue

        order.nfce_invoice = invoice
        order.fiscal_status = target_fs
        if target_fs == FoodOrder.FiscalStatus.REJECTED:
            order.fiscal_rejection_code = invoice.rejection_code or "rejected"
            order.fiscal_rejection_message = (invoice.rejection_message or "Rejeitada SEFAZ")[:255]
        elif target_fs == FoodOrder.FiscalStatus.FAILED:
            order.fiscal_rejection_code = invoice.rejection_code or "failed"
            order.fiscal_rejection_message = (invoice.rejection_message or "Falha emissão")[:255]
        elif target_fs == FoodOrder.FiscalStatus.AUTHORIZED:
            order.fiscal_rejection_code = ""
            order.fiscal_rejection_message = ""
        order.save(
            update_fields=[
                "nfce_invoice",
                "fiscal_status",
                "fiscal_rejection_code",
                "fiscal_rejection_message",
                "updated_at",
            ]
        )
        refresh_food_order_fiscal_state(order)
        from apps.food.fiscal.observability import audit_food_fiscal

        audit_food_fiscal(
            tenant=order.tenant,
            order=order,
            action=FoodFiscalEvent.Action.SYNC_NFCE,
            actor="nfce_sync",
            from_status=prev_fs,
            metadata={
                "nfce_invoice_id": str(invoice.id),
                "nfce_status": invoice.status,
            },
        )
        updated += 1
    return updated


def sync_food_orders_after_nfce_cancel(invoice: NfceInvoice) -> int:
    if invoice.status != NfceInvoice.Status.CANCELLED:
        return 0
    return sync_food_orders_from_nfce_invoice(invoice)


def cancel_nfce_for_food_order(
    *,
    tenant,
    order: FoodOrder,
    justificativa: str,
    actor: str,
) -> NfceInvoice:
    if order.channel != FoodOrder.Channel.IFOOD:
        raise FoodInvalidOrderError("Cancelamento fiscal só para pedidos iFood.")
    if order.tenant_id != tenant.id:
        raise FoodInvalidOrderError("Pedido não encontrado.")
    if not order.nfce_invoice_id:
        raise FoodInvalidOrderError("Pedido sem NFC-e vinculada.")
    inv = order.nfce_invoice
    if inv.tenant_id != tenant.id:
        raise FoodInvalidOrderError("NFC-e não encontrada.")
    from_status = order.fiscal_status
    cancel_nfce(inv, justificativa=justificativa, actor=actor)
    inv.refresh_from_db()
    sync_food_orders_after_nfce_cancel(inv)
    order.refresh_from_db()
    from apps.food.fiscal.observability import audit_food_fiscal

    audit_food_fiscal(
        tenant=tenant,
        order=order,
        action=FoodFiscalEvent.Action.CANCEL_NFCE,
        actor=actor,
        from_status=from_status,
        metadata={"nfce_invoice_id": str(inv.id)},
    )
    return inv
