"""Smoke QA Fase 1 — iFood fiscal stub (sucesso + exceção)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.food.exceptions import FoodInvalidOrderError, FoodOrderNotFoundError
from apps.food.fiscal.emit import emit_food_order_nfce, emit_food_orders_batch
from apps.food.fiscal.ignore import ignore_food_order_fiscal
from apps.food.fiscal.marketplace_sync import apply_marketplace_logistic_sync
from apps.food.fiscal.nfce_sync import cancel_nfce_for_food_order
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness
from apps.food.models import FoodFiscalEvent, FoodMarketplaceConnection, FoodOrder
from apps.food.operations import import_marketplace_order, sync_marketplace_connection, upsert_marketplace_connection
from apps.food.services import create_food_product
from apps.nfce.models import NfceInvoice


def _case(
    cid: str,
    title: str,
    *,
    kind: str,
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    started = timezone.now()
    row: dict[str, Any] = {
        "id": cid,
        "title": title,
        "kind": kind,
        "started_at": started.isoformat(),
    }
    try:
        outcome = fn()
        row.update(outcome)
        row["passed"] = bool(outcome.get("passed", False))
    except Exception as exc:  # noqa: BLE001 — smoke harness
        row["passed"] = False
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["finished_at"] = timezone.now().isoformat()
    return row


def _ensure_sku_stock(tenant: Tenant, sku: str, minimum: Decimal = Decimal("50")) -> None:
    from apps.food.models import FoodProduct, FoodStockMovement
    from apps.food.services import apply_stock_movement

    product = FoodProduct.objects.filter(tenant=tenant, sku=sku, is_active=True).first()
    if product is None:
        return
    product.stock_balance.refresh_from_db()
    available = product.stock_balance.quantity - product.stock_balance.reserved_quantity
    if available >= minimum:
        return
    apply_stock_movement(
        tenant=tenant,
        product=product,
        movement_type=FoodStockMovement.MovementType.IN,
        quantity=minimum - available,
        reason="qa-smoke-restock",
    )


def _import_ifood(
    tenant: Tenant,
    *,
    external_id: str,
    sku: str,
    price_cents: int = 1500,
    delivery: bool = False,
    customer_document: str = "39053344705",
) -> FoodOrder:
    _ensure_sku_stock(tenant, sku)
    order = import_marketplace_order(
        tenant=tenant,
        provider="ifood",
        external_order_id=external_id,
        customer_name=f"Cliente {external_id}",
        customer_phone="+5511999990001",
        lines=[{"sku": sku, "quantity": "1", "unit_price_cents": price_cents}],
        paid=True,
        delivery_address="Rua Teste 1" if delivery else "",
    )
    if delivery:
        order.fulfillment_mode = FoodOrder.FulfillmentMode.DELIVERY
        order.save(update_fields=["fulfillment_mode", "updated_at"])
    if customer_document:
        order.customer.document = customer_document
        order.customer.save(update_fields=["document"])
    elif delivery:
        order.customer.document = ""
        order.customer.save(update_fields=["document"])
    return order


def run_ifood_fiscal_smoke_suite(*, tenant: Tenant, phase: str = "all") -> dict[str, Any]:
    phase = (phase or "all").lower().strip()
    cases: list[dict[str, Any]] = []
    ctx: dict[str, Any] = {}

    if phase in {"1", "all"}:
        cases.extend(_phase1_cases(tenant, ctx))
    if phase in {"1b", "all"}:
        cases.extend(_phase1b_cases(tenant, ctx))

    passed = sum(1 for c in cases if c.get("passed"))
    failed = [c["id"] for c in cases if not c.get("passed")]
    label = {
        "1": "Fase 1 — stub lab (emissão)",
        "1b": "Fase 1b — stub lab (cancel iFood PO-3)",
        "all": "Fase 1 + 1b — stub lab",
    }.get(phase, phase)

    return {
        "tenant_slug": tenant.slug,
        "tenant_id": str(tenant.id),
        "phase": label,
        "generated_at": timezone.now().isoformat(),
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": len(failed),
            "failed_ids": failed,
        },
        "cases": cases,
        "phase_complete": len(failed) == 0,
    }


def _phase1_cases(tenant: Tenant, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def sm01_emit_pending():
        order = FoodOrder.objects.filter(
            tenant=tenant,
            channel=FoodOrder.Channel.IFOOD,
            fiscal_status=FoodOrder.FiscalStatus.PENDING,
        ).first()
        if order is None:
            order = _import_ifood(tenant, external_id="SM-01", sku="ALE-SKU")
        result = emit_food_order_nfce(tenant=tenant, order_id=order.id, actor="qa-smoke")
        order.refresh_from_db()
        inv = order.nfce_invoice
        events = FoodFiscalEvent.objects.filter(tenant=tenant, order=order).count()
        ctx["authorized_order_id"] = str(order.id)
        passed = (
            result.get("status") == "authorized"
            and order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
            and inv is not None
            and inv.status == "authorized"
            and events >= 1
        )
        return {
            "passed": passed,
            "result": result,
            "fiscal_status": order.fiscal_status,
            "nfce_status": inv.status if inv else None,
            "audit_events": events,
        }

    def sm02_idempotent_reemit():
        oid = ctx.get("authorized_order_id")
        if not oid:
            return {"passed": False, "reason": "missing SM-01 order"}
        result = emit_food_order_nfce(tenant=tenant, order_id=oid, actor="qa-smoke")
        return {
            "passed": result.get("status") == "skipped"
            and result.get("reason") == "already_authorized",
            "result": result,
        }

    def sm03_batch_partial():
        pending = _import_ifood(tenant, external_id="SM-03-P", sku="ALE-SKU")
        authorized_id = ctx.get("authorized_order_id")
        if not authorized_id:
            return {"passed": False, "reason": "missing SM-01 order"}
        summary = emit_food_orders_batch(
            tenant=tenant,
            order_ids=[authorized_id, pending.id],
            actor="qa-smoke",
        )
        pending.refresh_from_db()
        passed = (
            summary.get("authorized") == 1
            and summary.get("skipped") == 1
            and pending.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
        )
        return {"passed": passed, "summary": summary}

    def sm04_ignore_reemit():
        order = _import_ifood(tenant, external_id="SM-04", sku="ALE-SKU")
        ignore_food_order_fiscal(
            tenant=tenant,
            order_id=order.id,
            reason="QA smoke ignore",
            actor="qa-smoke",
        )
        order.refresh_from_db()
        if order.fiscal_status != FoodOrder.FiscalStatus.IGNORED:
            return {"passed": False, "reason": "ignore failed"}
        result = emit_food_order_nfce(tenant=tenant, order_id=order.id, actor="qa-smoke")
        order.refresh_from_db()
        passed = (
            result.get("status") == "authorized"
            and order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
        )
        return {"passed": passed, "result": result, "fiscal_status": order.fiscal_status}

    def sm05_readiness_happy():
        oid = ctx.get("authorized_order_id")
        order = FoodOrder.objects.get(pk=oid)
        warnings = assess_food_order_fiscal_readiness(order)
        error_codes = {w["code"] for w in warnings if w.get("level") == "error"}
        passed = "already_authorized" in {w["code"] for w in warnings} and not error_codes
        return {"passed": passed, "warnings": warnings}

    def ex01_not_ifood_channel():
        from apps.food.services import create_food_customer, create_order

        customer = create_food_customer(
            tenant=tenant,
            name="Cliente balcao",
            phone_e164="+5511888887777",
            document="39053344705",
        )
        product = FoodOrder.objects.filter(tenant=tenant).first().lines.first().product
        order = create_order(
            tenant=tenant,
            customer_id=customer.id,
            channel=FoodOrder.Channel.COUNTER,
            lines=[{"product_id": product.id, "quantity": "1"}],
            idempotency_key="qa-smoke-counter-1",
            await_pix=False,
        )
        result = emit_food_order_nfce(tenant=tenant, order_id=order.id, actor="qa-smoke")
        return {
            "passed": result.get("status") == "skipped"
            and result.get("reason") == "not_ifood_channel",
            "result": result,
        }

    def ex02_ignore_empty_reason():
        order = _import_ifood(tenant, external_id="EX-02", sku="ALE-SKU")
        try:
            ignore_food_order_fiscal(
                tenant=tenant,
                order_id=order.id,
                reason="",
                actor="qa-smoke",
            )
            return {"passed": False, "reason": "expected FoodInvalidOrderError"}
        except FoodInvalidOrderError as exc:
            return {"passed": True, "error": str(exc)}

    def ex03_ignore_authorized():
        oid = ctx.get("authorized_order_id")
        try:
            ignore_food_order_fiscal(
                tenant=tenant,
                order_id=oid,
                reason="nao deve",
                actor="qa-smoke",
            )
            return {"passed": False, "reason": "expected FoodInvalidOrderError"}
        except FoodInvalidOrderError as exc:
            return {"passed": True, "error": str(exc)}

    def ex04_unmapped_sku():
        create_food_product(
            tenant=tenant,
            sku="UNMAP-SKU",
            name="Sem de-para QA",
            price_cents=1200,
            cost_cents=500,
            unit="un",
            initial_stock=Decimal("10"),
        )
        order = _import_ifood(tenant, external_id="EX-04", sku="UNMAP-SKU")
        result = emit_food_order_nfce(tenant=tenant, order_id=order.id, actor="qa-smoke")
        order.refresh_from_db()
        passed = (
            result.get("status") == "failed"
            and result.get("code") == "adapter_error"
            and order.fiscal_status == FoodOrder.FiscalStatus.FAILED
        )
        return {"passed": passed, "result": result, "fiscal_status": order.fiscal_status}

    def ex05_batch_not_found():
        import uuid

        fake_id = uuid.uuid4()
        summary = emit_food_orders_batch(
            tenant=tenant,
            order_ids=[fake_id],
            actor="qa-smoke",
        )
        row = summary["results"][0]
        passed = row.get("code") == "not_found" and summary.get("failed") == 1
        return {"passed": passed, "summary": summary}

    def ex06_delivery_no_cpf_warn():
        order = _import_ifood(
            tenant,
            external_id="EX-06",
            sku="ALE-SKU",
            delivery=True,
            customer_document="",
        )
        warnings = assess_food_order_fiscal_readiness(order)
        codes = {w["code"] for w in warnings}
        passed = "delivery_requires_identification" in codes
        return {"passed": passed, "warnings": warnings}

    def ex07_cross_tenant_isolation():
        other = Tenant.objects.exclude(pk=tenant.pk).first()
        if other is None:
            return {"passed": True, "skipped": True, "reason": "no second tenant"}
        oid = ctx.get("authorized_order_id")
        try:
            emit_food_order_nfce(tenant=other, order_id=oid, actor="qa-smoke")
            return {"passed": False, "reason": "expected FoodOrderNotFoundError"}
        except FoodOrderNotFoundError as exc:
            return {"passed": True, "error": str(exc)}

    suite = [
        ("SM-01", "Emitir pedido pending -> AUTHORIZED + NFC-e stub", "success", sm01_emit_pending),
        ("SM-02", "Reemitir pedido authorized -> skip already_authorized", "success", sm02_idempotent_reemit),
        ("SM-03", "Lote parcial: 1 skip + 1 authorized (PO-4)", "success", sm03_batch_partial),
        ("SM-04", "Ignore -> reemit direto -> AUTHORIZED (PO ignore)", "success", sm04_ignore_reemit),
        ("SM-05", "Readiness pedido authorized -> info, sem errors", "success", sm05_readiness_happy),
        ("EX-01", "Canal balcao -> skip not_ifood_channel", "exception", ex01_not_ifood_channel),
        ("EX-02", "Ignore sem motivo -> FoodInvalidOrderError", "exception", ex02_ignore_empty_reason),
        ("EX-03", "Ignore em authorized -> FoodInvalidOrderError", "exception", ex03_ignore_authorized),
        ("EX-04", "SKU sem de-para -> failed adapter_error", "exception", ex04_unmapped_sku),
        ("EX-05", "Batch order inexistente -> not_found", "exception", ex05_batch_not_found),
        ("EX-06", "Delivery sem CPF -> warn informativo (PO-2)", "exception", ex06_delivery_no_cpf_warn),
        ("EX-07", "Emit cross-tenant -> FoodOrderNotFoundError", "exception", ex07_cross_tenant_isolation),
    ]

    for cid, title, kind, fn in suite:
        cases.append(_case(cid, title, kind=kind, fn=fn))

    return cases


def _phase1b_cases(tenant: Tenant, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    import uuid

    cases: list[dict[str, Any]] = []
    _ensure_sku_stock(tenant, "ALE-SKU")
    run_suffix = uuid.uuid4().hex[:6]

    def sm06_cancel_pre_emission():
        order = _import_ifood(tenant, external_id="SM-06", sku="ALE-SKU")
        assert order.fiscal_status == FoodOrder.FiscalStatus.PENDING
        row = apply_marketplace_logistic_sync(
            tenant=tenant,
            provider="ifood",
            payload={"external_order_id": "SM-06", "cancelled": True},
        )
        order.refresh_from_db()
        codes = {w["code"] for w in assess_food_order_fiscal_readiness(order)}
        passed = (
            row["action"] == "cancelled"
            and order.status == FoodOrder.Status.CANCELLED
            and order.fiscal_status == FoodOrder.FiscalStatus.PENDING
            and "order_logistic_cancelled" in codes
            and "marketplace_cancelled_with_nfce" not in codes
        )
        return {"passed": passed, "sync": row, "fiscal_status": order.fiscal_status}

    def sm07_cancel_post_authorized_po3():
        ext = f"SM-07-{run_suffix}"
        order = _import_ifood(tenant, external_id=ext, sku="ALE-SKU")
        emit = emit_food_order_nfce(tenant=tenant, order_id=order.id, actor="qa-smoke-1b")
        order.refresh_from_db()
        nfce_id = order.nfce_invoice_id
        row = apply_marketplace_logistic_sync(
            tenant=tenant,
            provider="ifood",
            payload={"external_order_id": ext, "cancelled": True},
        )
        order.refresh_from_db()
        codes = {w.get("code") for w in (order.fiscal_warnings or [])}
        passed = (
            emit.get("status") == "authorized"
            and row["action"] == "cancelled"
            and row.get("requires_manual_nfce_cancel") is True
            and order.status == FoodOrder.Status.CANCELLED
            and order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED
            and order.nfce_invoice_id == nfce_id
            and "marketplace_cancelled_with_nfce" in codes
        )
        ctx["cancelled_authorized_order_id"] = str(order.id)
        return {
            "passed": passed,
            "sync": row,
            "nfce_invoice_id": str(nfce_id) if nfce_id else None,
        }

    def sm08_stub_sync_cancel_pipeline():
        mp_mode = (getattr(settings, "MARKETPLACE_HTTP_MODE", "stub") or "stub").lower()
        ext = f"SM-08-{run_suffix}"
        conn = upsert_marketplace_connection(
            tenant=tenant,
            provider="ifood",
            merchant_ref=f"ale-smoke-cancel-{run_suffix}",
            settings={
                "http_mode": mp_mode,
                "stub_orders": [
                    {
                        "external_order_id": ext,
                        "customer_name": "Sync cancel",
                        "lines": [{"sku": "ALE-SKU", "quantity": "1", "unit_price_cents": 1500}],
                        "paid": True,
                    },
                    {"external_order_id": ext, "cancelled": True},
                ],
            },
        )
        first = sync_marketplace_connection(tenant=tenant, connection=conn)
        second = sync_marketplace_connection(tenant=tenant, connection=conn)
        order = FoodOrder.objects.get(tenant=tenant, channel_ref=ext)
        passed = (
            first.get("imported") >= 1
            and second.get("updated", 0) >= 1
            and order.status == FoodOrder.Status.CANCELLED
            and order.fiscal_status == FoodOrder.FiscalStatus.PENDING
        )
        return {"passed": passed, "first_sync": first, "second_sync": second}

    def sm09_manual_nfce_cancel_after_ifood():
        ext = f"SM-09-{run_suffix}"
        order = _import_ifood(tenant, external_id=ext, sku="ALE-SKU")
        emit = emit_food_order_nfce(tenant=tenant, order_id=order.id, actor="qa-smoke-1b")
        order.refresh_from_db()
        if emit.get("status") != "authorized":
            return {
                "passed": False,
                "reason": "emit_not_authorized",
                "emit": emit,
                "fiscal_status": order.fiscal_status,
            }
        apply_marketplace_logistic_sync(
            tenant=tenant,
            provider="ifood",
            payload={"external_order_id": ext, "cancelled": True},
        )
        order.refresh_from_db()
        inv = cancel_nfce_for_food_order(
            tenant=tenant,
            order=order,
            justificativa="Cancelamento manual QA pos cancel iFood",
            actor="qa-smoke-1b",
        )
        order.refresh_from_db()
        passed = (
            order.status == FoodOrder.Status.CANCELLED
            and inv.status == NfceInvoice.Status.CANCELLED
            and order.fiscal_status == FoodOrder.FiscalStatus.CANCELLED
        )
        return {
            "passed": passed,
            "emit": emit,
            "nfce_status": inv.status,
            "fiscal_status": order.fiscal_status,
        }

    def ex08_cancel_unknown_order():
        row = apply_marketplace_logistic_sync(
            tenant=tenant,
            provider="ifood",
            payload={"external_order_id": "UNKNOWN-SM-1B", "cancelled": True},
        )
        return {
            "passed": row["action"] == "skipped" and row["code"] == "order_not_found",
            "sync": row,
        }

    def ex09_cancel_idempotent():
        order = _import_ifood(tenant, external_id="EX-09", sku="ALE-SKU")
        row1 = apply_marketplace_logistic_sync(
            tenant=tenant,
            provider="ifood",
            payload={"external_order_id": "EX-09", "cancelled": True},
        )
        order.refresh_from_db()
        row2 = apply_marketplace_logistic_sync(
            tenant=tenant,
            provider="ifood",
            payload={"external_order_id": "EX-09", "cancelled": True},
        )
        passed = (
            row1["action"] == "cancelled"
            and row2["action"] == "cancelled"
            and order.status == FoodOrder.Status.CANCELLED
        )
        return {"passed": passed, "first": row1, "second": row2}

    suite = [
        ("SM-06", "Cancel pre-emissao: logistic cancelled, fiscal PENDING (EX-ING-07)", "success", sm06_cancel_pre_emission),
        ("SM-07", "Cancel pos-AUTHORIZED: NFC-e intacta + aviso manual (PO-3)", "success", sm07_cancel_post_authorized_po3),
        ("SM-08", "Stub sync: import + cancel event via polling", "success", sm08_stub_sync_cancel_pipeline),
        ("SM-09", "Cancel manual NFC-e apos cancel iFood (runbook PO-3)", "success", sm09_manual_nfce_cancel_after_ifood),
        ("EX-08", "Cancel pedido inexistente -> skipped order_not_found", "exception", ex08_cancel_unknown_order),
        ("EX-09", "Cancel iFood idempotente (2x mesmo evento)", "exception", ex09_cancel_idempotent),
    ]

    for cid, title, kind, fn in suite:
        cases.append(_case(cid, title, kind=kind, fn=fn))

    return cases
