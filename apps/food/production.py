"""Fase 3 — BOM, produção, capacidade e MRP lite."""

from __future__ import annotations

from datetime import date, time
from decimal import ROUND_CEILING, Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.food.exceptions import (
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodProductNotFoundError,
)
from apps.food.models import (
    FoodBom,
    FoodBomComponent,
    FoodCapacitySlot,
    FoodProduct,
    FoodProductionOrder,
    FoodStockBalance,
    FoodStockMovement,
)
from apps.food.services import apply_stock_movement


def _uuid(value) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise FoodInvalidOrderError(f"id inválido: {value}") from exc


def create_bom(
    *,
    tenant,
    product_id,
    name: str,
    components: list[dict[str, Any]],
    expected_yield_bps: int = 10000,
) -> FoodBom:
    """
    components: [{product_id, quantity_per_unit, scrap_bps?}, ...]
    """
    name = (name or "").strip()
    if not name:
        raise FoodInvalidOrderError("Nome da ficha técnica é obrigatório.")
    if not components:
        raise FoodInvalidOrderError("BOM precisa de ao menos um componente.")
    product = FoodProduct.objects.filter(
        tenant=tenant, pk=_uuid(product_id), is_active=True
    ).first()
    if product is None:
        raise FoodProductNotFoundError("Produto acabado não encontrado.")
    if expected_yield_bps < 1 or expected_yield_bps > 10000:
        raise FoodInvalidOrderError("expected_yield_bps inválido.")

    with transaction.atomic():
        FoodBom.objects.filter(
            tenant=tenant, product=product, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        bom = FoodBom.objects.create(
            tenant=tenant,
            product=product,
            name=name,
            expected_yield_bps=expected_yield_bps,
            is_active=True,
        )
        for row in components:
            comp = FoodProduct.objects.filter(
                tenant=tenant, pk=_uuid(row.get("product_id")), is_active=True
            ).first()
            if comp is None:
                raise FoodProductNotFoundError(
                    f"Insumo não encontrado: {row.get('product_id')}"
                )
            if comp.id == product.id:
                raise FoodInvalidOrderError("Produto não pode ser insumo de si mesmo.")
            qty = Decimal(str(row.get("quantity_per_unit", 0)))
            if qty <= 0:
                raise FoodInvalidOrderError("quantity_per_unit deve ser > 0.")
            scrap = int(row.get("scrap_bps") or 0)
            FoodBomComponent.objects.create(
                tenant=tenant,
                bom=bom,
                product=comp,
                quantity_per_unit=qty,
                scrap_bps=scrap,
            )
    return bom


def explode_bom(*, bom: FoodBom, quantity: Decimal | int | str) -> list[dict]:
    """Qtd de cada insumo necessária (inclui scrap planejado)."""
    qty_fg = Decimal(str(quantity))
    if qty_fg <= 0:
        raise FoodInvalidOrderError("Quantidade de explosão deve ser > 0.")
    rows = []
    for c in bom.components.select_related("product"):
        base = c.quantity_per_unit * qty_fg
        with_scrap = base * (Decimal("1") + Decimal(c.scrap_bps) / Decimal("10000"))
        rows.append(
            {
                "product": c.product,
                "product_id": c.product_id,
                "sku": c.product.sku,
                "quantity": with_scrap.quantize(Decimal("0.0001")),
            }
        )
    return rows


def create_capacity_slot(
    *,
    tenant,
    service_date: date,
    starts_at: time,
    ends_at: time,
    capacity_units: int = 10,
    name: str = "",
) -> FoodCapacitySlot:
    if capacity_units < 1:
        raise FoodInvalidOrderError("capacity_units deve ser >= 1.")
    if ends_at <= starts_at:
        raise FoodInvalidOrderError("ends_at deve ser após starts_at.")
    return FoodCapacitySlot.objects.create(
        tenant=tenant,
        service_date=service_date,
        starts_at=starts_at,
        ends_at=ends_at,
        capacity_units=capacity_units,
        name=(name or "").strip(),
    )


def create_production_order(
    *,
    tenant,
    product_id,
    quantity_planned: Decimal | int | str,
    idempotency_key: str,
    bom_id=None,
    capacity_slot_id=None,
    notes: str = "",
) -> FoodProductionOrder:
    key = (idempotency_key or "").strip()
    if not key:
        raise FoodInvalidOrderError("idempotency_key é obrigatória.")
    existing = FoodProductionOrder.objects.filter(
        tenant=tenant, idempotency_key=key
    ).first()
    if existing is not None:
        return existing

    product = FoodProduct.objects.filter(
        tenant=tenant, pk=_uuid(product_id), is_active=True
    ).first()
    if product is None:
        raise FoodProductNotFoundError("Produto acabado não encontrado.")
    qty = Decimal(str(quantity_planned))
    if qty <= 0:
        raise FoodInvalidOrderError("quantity_planned deve ser > 0.")

    if bom_id:
        bom = FoodBom.objects.filter(
            tenant=tenant, pk=_uuid(bom_id), product=product, is_active=True
        ).first()
    else:
        bom = FoodBom.objects.filter(
            tenant=tenant, product=product, is_active=True
        ).first()
    if bom is None:
        raise FoodInvalidOrderError("Nenhuma ficha técnica ativa para o produto.")

    slot = None
    units = int(qty.to_integral_value(rounding=ROUND_CEILING))
    if capacity_slot_id:
        slot = FoodCapacitySlot.objects.filter(
            tenant=tenant, pk=_uuid(capacity_slot_id)
        ).first()
        if slot is None:
            raise FoodInvalidOrderError("Slot de capacidade não encontrado.")
        if units > slot.free_units:
            raise FoodInvalidOrderError(
                f"Capacidade insuficiente no slot "
                f"(livre={slot.free_units}, ped={units})."
            )

    try:
        with transaction.atomic():
            if slot is not None:
                locked = FoodCapacitySlot.objects.select_for_update().get(pk=slot.pk)
                if units > locked.free_units:
                    raise FoodInvalidOrderError("Capacidade do slot esgotada.")
                locked.booked_units = locked.booked_units + units
                locked.save(update_fields=["booked_units", "updated_at"])
                slot = locked
            op = FoodProductionOrder.objects.create(
                tenant=tenant,
                product=product,
                bom=bom,
                capacity_slot=slot,
                quantity_planned=qty,
                idempotency_key=key,
                notes=notes or "",
                yield_bps=bom.expected_yield_bps,
            )
    except IntegrityError:
        again = FoodProductionOrder.objects.filter(
            tenant=tenant, idempotency_key=key
        ).first()
        if again is not None:
            return again
        raise
    return op


def start_production(*, tenant, production_order_id) -> FoodProductionOrder:
    """Consome insumos do BOM (baixa física) e marca OP em andamento."""
    with transaction.atomic():
        op = (
            FoodProductionOrder.objects.select_for_update()
            .select_related("bom")
            .filter(tenant=tenant, pk=production_order_id)
            .first()
        )
        if op is None:
            raise FoodInvalidOrderError("Ordem de produção não encontrada.")
        if op.status == FoodProductionOrder.Status.IN_PROGRESS:
            return op
        if op.status != FoodProductionOrder.Status.PLANNED:
            raise FoodInvalidTransitionError(
                f"Não é possível iniciar OP em status {op.status}."
            )
        needs = explode_bom(bom=op.bom, quantity=op.quantity_planned)
        for row in needs:
            apply_stock_movement(
                tenant=tenant,
                product=row["product"],
                movement_type=FoodStockMovement.MovementType.OUT,
                quantity=row["quantity"],
                reason=f"producao_start:{op.id}",
            )
        op.status = FoodProductionOrder.Status.IN_PROGRESS
        op.started_at = timezone.now()
        op.save(update_fields=["status", "started_at", "updated_at"])
    return op


def complete_production(
    *,
    tenant,
    production_order_id,
    quantity_produced: Decimal | int | str | None = None,
) -> FoodProductionOrder:
    """
    Encerra OP: entra produto acabado com rendimento/perdas.
    quantity_produced default = planned * yield_bps/10000 do BOM.
    """
    with transaction.atomic():
        op = (
            FoodProductionOrder.objects.select_for_update()
            .select_related("bom", "product")
            .filter(tenant=tenant, pk=production_order_id)
            .first()
        )
        if op is None:
            raise FoodInvalidOrderError("Ordem de produção não encontrada.")
        if op.status == FoodProductionOrder.Status.DONE:
            return op
        if op.status != FoodProductionOrder.Status.IN_PROGRESS:
            raise FoodInvalidTransitionError(
                f"Só conclui OP em progresso (atual={op.status})."
            )

        if quantity_produced is None:
            produced = (
                op.quantity_planned
                * Decimal(op.bom.expected_yield_bps)
                / Decimal("10000")
            ).quantize(Decimal("0.001"))
        else:
            produced = Decimal(str(quantity_produced))
        if produced < 0:
            raise FoodInvalidOrderError("quantity_produced inválida.")

        loss = max(Decimal("0"), op.quantity_planned - produced)
        yield_bps = 0
        if op.quantity_planned > 0:
            yield_bps = int(
                (produced * Decimal("10000") / op.quantity_planned).quantize(
                    Decimal("1")
                )
            )
            yield_bps = min(10000, max(0, yield_bps))

        if produced > 0:
            apply_stock_movement(
                tenant=tenant,
                product=op.product,
                movement_type=FoodStockMovement.MovementType.IN,
                quantity=produced,
                reason=f"producao_done:{op.id}",
            )

        op.quantity_produced = produced
        op.loss_quantity = loss
        op.yield_bps = yield_bps
        op.status = FoodProductionOrder.Status.DONE
        op.completed_at = timezone.now()
        op.save(
            update_fields=[
                "quantity_produced",
                "loss_quantity",
                "yield_bps",
                "status",
                "completed_at",
                "updated_at",
            ]
        )
    return op


def mrp_suggestions(*, tenant, limit: int = 50) -> list[dict]:
    """
    MRP lite: produtos acabados com BOM cujo disponível < min → sugere OP.
    """
    suggestions = []
    boms = (
        FoodBom.objects.filter(tenant=tenant, is_active=True)
        .select_related("product")
        .prefetch_related("components__product")[:200]
    )
    for bom in boms:
        bal = FoodStockBalance.objects.filter(product=bom.product).first()
        available = Decimal("0")
        min_q = Decimal("0")
        if bal is not None:
            available = bal.available_quantity
            min_q = bal.min_quantity
        if available >= min_q and min_q > 0:
            continue
        if min_q <= 0 and available > 0:
            continue
        need = max(min_q - available, Decimal("1")) if min_q > 0 else Decimal("1")
        # verifica insumos
        components = explode_bom(bom=bom, quantity=need)
        shortages = []
        for row in components:
            cbal = FoodStockBalance.objects.filter(product_id=row["product_id"]).first()
            cav = cbal.available_quantity if cbal else Decimal("0")
            if cav < row["quantity"]:
                shortages.append(
                    {
                        "sku": row["sku"],
                        "need": str(row["quantity"]),
                        "available": str(cav),
                    }
                )
        suggestions.append(
            {
                "product_id": str(bom.product_id),
                "sku": bom.product.sku,
                "bom_id": str(bom.id),
                "available": str(available),
                "min_quantity": str(min_q),
                "suggested_qty": str(need),
                "component_shortages": shortages,
                "can_start": len(shortages) == 0,
            }
        )
        if len(suggestions) >= limit:
            break
    return suggestions
