"""Emissão supervisionada iFood → NFC-e (lote parcial PO-4 / B5 hardening)."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from apps.food.exceptions import FoodInvalidOrderError, FoodOrderNotFoundError
from apps.food.fiscal.adapter import (
    build_nfce_items_from_food_order,
    food_order_delivery_flag,
)
from apps.food.fiscal.ident import resolve_food_order_customer_ident
from apps.food.fiscal.ignore import prepare_ignored_order_for_reemit
from apps.food.fiscal.readiness import refresh_food_order_fiscal_state, resolve_emit_provider
from apps.food.models import FoodFiscalEvent, FoodOrder
from apps.nfce.exceptions import NfceDomainError
from apps.nfce.models import NfceInvoice
from apps.nfce.services import checkout_and_emit_nfce

EMITTABLE_FISCAL = frozenset(
    {
        FoodOrder.FiscalStatus.PENDING,
        FoodOrder.FiscalStatus.REJECTED,
        FoodOrder.FiscalStatus.FAILED,
        "",
    }
)

_IN_FLIGHT_NFCE = frozenset(
    {
        NfceInvoice.Status.SUBMITTING,
        NfceInvoice.Status.POLLING,
    }
)


def food_order_idempotency_key(order: FoodOrder) -> str:
    attempt = int(order.fiscal_emit_attempt or 0)
    if attempt <= 0:
        return f"food:ifood:{order.id}"
    return f"food:ifood:{order.id}:a{attempt}"


def map_invoice_to_food_fiscal_status(inv: NfceInvoice) -> str:
    if inv.status == NfceInvoice.Status.AUTHORIZED:
        return FoodOrder.FiscalStatus.AUTHORIZED
    if inv.status == NfceInvoice.Status.REJECTED:
        return FoodOrder.FiscalStatus.REJECTED
    if inv.status == NfceInvoice.Status.CANCELLED:
        return FoodOrder.FiscalStatus.CANCELLED
    if inv.status in _IN_FLIGHT_NFCE:
        return FoodOrder.FiscalStatus.PROCESSING
    return FoodOrder.FiscalStatus.FAILED


def _find_existing_nfce(*, tenant, order: FoodOrder) -> NfceInvoice | None:
    if order.nfce_invoice_id:
        inv = order.nfce_invoice
        if inv and inv.tenant_id == tenant.id:
            return inv
    key = food_order_idempotency_key(order)
    inv = NfceInvoice.objects.filter(tenant=tenant, idempotency_key=key).first()
    if inv is not None:
        return inv
    base = f"food:ifood:{order.id}"
    if key != base:
        return NfceInvoice.objects.filter(tenant=tenant, idempotency_key=base).first()
    return None


def _apply_nfce_to_order(order: FoodOrder, inv: NfceInvoice) -> None:
    fs = map_invoice_to_food_fiscal_status(inv)
    order.nfce_invoice = inv
    order.fiscal_status = fs
    if fs == FoodOrder.FiscalStatus.REJECTED:
        order.fiscal_rejection_code = inv.rejection_code or "rejected"
        order.fiscal_rejection_message = (inv.rejection_message or "Rejeitada SEFAZ")[:255]
    elif fs == FoodOrder.FiscalStatus.FAILED:
        order.fiscal_rejection_code = inv.rejection_code or "failed"
        order.fiscal_rejection_message = (inv.rejection_message or "Falha emissão")[:255]
    elif fs == FoodOrder.FiscalStatus.AUTHORIZED:
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


def _replay_existing_nfce(*, tenant, order: FoodOrder) -> dict[str, Any] | None:
    inv = _find_existing_nfce(tenant=tenant, order=order)
    if inv is None:
        return None

    fs = map_invoice_to_food_fiscal_status(inv)
    if fs == FoodOrder.FiscalStatus.AUTHORIZED:
        _apply_nfce_to_order(order, inv)
        return {
            "order_id": str(order.id),
            "status": "skipped",
            "reason": "already_authorized",
            "nfce_invoice_id": str(inv.id),
        }
    if fs == FoodOrder.FiscalStatus.PROCESSING:
        _apply_nfce_to_order(order, inv)
        return {
            "order_id": str(order.id),
            "status": "skipped",
            "reason": "processing",
            "nfce_invoice_id": str(inv.id),
        }
    if fs in {FoodOrder.FiscalStatus.REJECTED, FoodOrder.FiscalStatus.FAILED}:
        if inv.idempotency_key == food_order_idempotency_key(order):
            _apply_nfce_to_order(order, inv)
            return {
                "order_id": str(order.id),
                "status": fs,
                "nfce_invoice_id": str(inv.id),
                "code": inv.rejection_code or fs,
                "message": inv.rejection_message or "",
            }
    return None


def _audit_emit_result(
    *,
    tenant,
    order: FoodOrder,
    from_status: str,
    actor: str,
    result: dict[str, Any],
) -> None:
    if order.channel != FoodOrder.Channel.IFOOD:
        return
    from apps.food.fiscal.observability import audit_food_fiscal

    st = result.get("status")
    action = (
        FoodFiscalEvent.Action.EMIT_SKIP
        if st == "skipped"
        else FoodFiscalEvent.Action.EMIT_DONE
    )
    audit_food_fiscal(
        tenant=tenant,
        order=order,
        action=action,
        actor=actor,
        from_status=from_status,
        metadata={
            "result_status": st,
            "reason": result.get("reason") or result.get("code"),
            "message": result.get("message"),
            "nfce_invoice_id": result.get("nfce_invoice_id"),
        },
    )


@transaction.atomic
def emit_food_order_nfce(
    *,
    tenant,
    order_id,
    actor: str = "ifood_batch",
) -> dict[str, Any]:
    order = (
        FoodOrder.objects.select_for_update()
        .filter(tenant=tenant, pk=order_id)
        .select_related("nfce_invoice")
        .first()
    )
    if order is None:
        raise FoodOrderNotFoundError("Pedido não encontrado.")

    from_status = order.fiscal_status or ""

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        _audit_emit_result(
            tenant=tenant,
            order=order,
            from_status=from_status,
            actor=actor,
            result=payload,
        )
        return payload

    if order.channel != FoodOrder.Channel.IFOOD:
        return finish(
            {
                "order_id": str(order.id),
                "status": "skipped",
                "reason": "not_ifood_channel",
            }
        )

    if order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED:
        return finish(
            {
                "order_id": str(order.id),
                "status": "skipped",
                "reason": "already_authorized",
                "nfce_invoice_id": str(order.nfce_invoice_id) if order.nfce_invoice_id else None,
            }
        )

    if order.fiscal_status == FoodOrder.FiscalStatus.PROCESSING:
        replay = _replay_existing_nfce(tenant=tenant, order=order)
        if replay is not None:
            return finish(replay)
        return finish(
            {
                "order_id": str(order.id),
                "status": "skipped",
                "reason": "processing",
            }
        )

    if order.fiscal_status == FoodOrder.FiscalStatus.IGNORED:
        prepare_ignored_order_for_reemit(order)

    if order.fiscal_status not in EMITTABLE_FISCAL:
        return finish(
            {
                "order_id": str(order.id),
                "status": "skipped",
                "reason": f"fiscal_status_{order.fiscal_status}",
            }
        )

    replay = _replay_existing_nfce(tenant=tenant, order=order)
    if replay is not None:
        if replay.get("status") == "skipped":
            return finish(replay)
        if replay.get("status") in {
            FoodOrder.FiscalStatus.REJECTED,
            FoodOrder.FiscalStatus.FAILED,
        }:
            return finish(replay)

    provider = resolve_emit_provider(tenant=tenant, order=order)
    if provider is None:
        order.fiscal_status = FoodOrder.FiscalStatus.FAILED
        order.fiscal_rejection_code = "no_provider"
        order.fiscal_rejection_message = "Nenhum emitente ativo."
        order.save(
            update_fields=[
                "fiscal_status",
                "fiscal_rejection_code",
                "fiscal_rejection_message",
                "updated_at",
            ]
        )
        refresh_food_order_fiscal_state(order)
        return finish(
            {
                "order_id": str(order.id),
                "status": "failed",
                "code": "no_provider",
            }
        )

    if order.fiscal_status in {
        FoodOrder.FiscalStatus.REJECTED,
        FoodOrder.FiscalStatus.FAILED,
    }:
        order.fiscal_emit_attempt = int(order.fiscal_emit_attempt or 0) + 1

    order.fiscal_status = FoodOrder.FiscalStatus.PROCESSING
    order.fiscal_rejection_code = ""
    order.fiscal_rejection_message = ""
    order.save(
        update_fields=[
            "fiscal_status",
            "fiscal_emit_attempt",
            "fiscal_rejection_code",
            "fiscal_rejection_message",
            "updated_at",
        ]
    )
    from apps.food.fiscal.observability import audit_food_fiscal

    audit_food_fiscal(
        tenant=tenant,
        order=order,
        action=FoodFiscalEvent.Action.EMIT_START,
        actor=actor,
        from_status=from_status,
        to_status=FoodOrder.FiscalStatus.PROCESSING,
    )

    try:
        items = build_nfce_items_from_food_order(order)
        cpf, cnpj = resolve_food_order_customer_ident(order)
        inv = checkout_and_emit_nfce(
            tenant=tenant,
            provider=provider,
            items=items,
            idempotency_key=food_order_idempotency_key(order),
            cpf=cpf,
            cnpj=cnpj,
            delivery=food_order_delivery_flag(order),
            actor=actor,
        )
    except NfceDomainError as exc:
        order.fiscal_status = FoodOrder.FiscalStatus.FAILED
        order.fiscal_rejection_code = getattr(exc, "code", "nfce_error") or "nfce_error"
        order.fiscal_rejection_message = str(exc)[:255]
        order.save(
            update_fields=[
                "fiscal_status",
                "fiscal_rejection_code",
                "fiscal_rejection_message",
                "updated_at",
            ]
        )
        refresh_food_order_fiscal_state(order)
        return finish(
            {
                "order_id": str(order.id),
                "status": "failed",
                "code": order.fiscal_rejection_code,
                "message": order.fiscal_rejection_message,
            }
        )
    except FoodInvalidOrderError as exc:
        order.fiscal_status = FoodOrder.FiscalStatus.FAILED
        order.fiscal_rejection_code = "adapter_error"
        order.fiscal_rejection_message = str(exc)[:255]
        order.save(
            update_fields=[
                "fiscal_status",
                "fiscal_rejection_code",
                "fiscal_rejection_message",
                "updated_at",
            ]
        )
        refresh_food_order_fiscal_state(order)
        return finish(
            {
                "order_id": str(order.id),
                "status": "failed",
                "code": "adapter_error",
                "message": order.fiscal_rejection_message,
            }
        )

    if isinstance(inv, dict) and inv.get("route") == "nfe":
        order.fiscal_status = FoodOrder.FiscalStatus.FAILED
        order.fiscal_rejection_code = "policy_nfe"
        order.fiscal_rejection_message = "Política exige NF-e 55 (PO-1: só NFC-e)."
        order.save(
            update_fields=[
                "fiscal_status",
                "fiscal_rejection_code",
                "fiscal_rejection_message",
                "updated_at",
            ]
        )
        refresh_food_order_fiscal_state(order)
        return finish(
            {
                "order_id": str(order.id),
                "status": "failed",
                "code": "policy_nfe",
                "message": order.fiscal_rejection_message,
            }
        )

    _apply_nfce_to_order(order, inv)
    fs = order.fiscal_status
    return finish(
        {
            "order_id": str(order.id),
            "status": "authorized" if fs == FoodOrder.FiscalStatus.AUTHORIZED else fs,
            "nfce_invoice_id": str(inv.id),
            "access_key": inv.access_key or "",
        }
    )


def emit_food_orders_batch(
    *,
    tenant,
    order_ids: list,
    actor: str = "ifood_batch",
    batch_id: str | None = None,
) -> dict[str, Any]:
    bid = batch_id or str(uuid.uuid4())
    results: list[dict[str, Any]] = []
    summary = {"batch_id": bid, "total": 0, "authorized": 0, "failed": 0, "skipped": 0}

    for oid in order_ids:
        summary["total"] += 1
        try:
            row = emit_food_order_nfce(tenant=tenant, order_id=oid, actor=actor)
        except FoodOrderNotFoundError as exc:
            row = {"order_id": str(oid), "status": "failed", "code": "not_found", "message": str(exc)}
        results.append(row)
        st = row.get("status")
        if st == "authorized":
            summary["authorized"] += 1
        elif st == "skipped":
            summary["skipped"] += 1
        else:
            summary["failed"] += 1

    summary["results"] = results
    from apps.food.fiscal.observability import log_fiscal_batch_summary

    log_fiscal_batch_summary(tenant=tenant, batch_id=bid, summary=summary, actor=actor)
    return summary
