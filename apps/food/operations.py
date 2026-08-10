"""Fase 2 — compras, delivery e marketplace (Order Service unificado)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.food.exceptions import (
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodOrderNotFoundError,
    FoodProductNotFoundError,
)
from apps.food.models import (
    FoodCustomer,
    FoodDeliveryRoute,
    FoodDeliveryStop,
    FoodMarketplaceConnection,
    FoodOrder,
    FoodProduct,
    FoodPurchase,
    FoodPurchaseLine,
    FoodStockMovement,
    FoodSupplier,
)
from apps.food.services import (
    apply_stock_movement,
    create_food_customer,
    create_order,
)


def _uuid(value):
    if value is None:
        raise FoodProductNotFoundError("product_id ausente.")
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise FoodProductNotFoundError(f"product_id inválido: {value}") from exc


# confirmed → preparing → ready → fulfilled
ORDER_TRANSITIONS: dict[str, set[str]] = {
    FoodOrder.Status.CONFIRMED: {FoodOrder.Status.PREPARING, FoodOrder.Status.CANCELLED},
    FoodOrder.Status.PREPARING: {FoodOrder.Status.READY, FoodOrder.Status.CANCELLED},
    FoodOrder.Status.READY: {
        FoodOrder.Status.FULFILLED,
        FoodOrder.Status.PREPARING,
        FoodOrder.Status.CANCELLED,
    },
    FoodOrder.Status.PENDING_PAYMENT: {FoodOrder.Status.CANCELLED},
    FoodOrder.Status.DRAFT: {FoodOrder.Status.CANCELLED, FoodOrder.Status.CONFIRMED},
}


def create_supplier(
    *,
    tenant,
    name: str,
    document: str = "",
    phone: str = "",
    email: str = "",
    notes: str = "",
) -> FoodSupplier:
    name = (name or "").strip()
    if not name:
        raise FoodInvalidOrderError("Nome do fornecedor é obrigatório.")
    return FoodSupplier.objects.create(
        tenant=tenant,
        name=name,
        document="".join(c for c in (document or "") if c.isdigit()),
        phone=(phone or "").strip(),
        email=(email or "").strip(),
        notes=notes or "",
    )


def create_purchase(
    *,
    tenant,
    supplier_id,
    lines: list[dict[str, Any]],
    idempotency_key: str,
    expected_at: date | None = None,
    notes: str = "",
    mark_ordered: bool = True,
) -> FoodPurchase:
    key = (idempotency_key or "").strip()
    if not key:
        raise FoodInvalidOrderError("idempotency_key da compra é obrigatória.")
    existing = FoodPurchase.objects.filter(tenant=tenant, idempotency_key=key).first()
    if existing is not None:
        return existing
    supplier = FoodSupplier.objects.filter(
        tenant=tenant, pk=supplier_id, is_active=True
    ).first()
    if supplier is None:
        raise FoodInvalidOrderError("Fornecedor não encontrado.")
    if not lines:
        raise FoodInvalidOrderError("Compra precisa de ao menos um item.")

    prepared: list[tuple[FoodProduct, Decimal, int, int]] = []
    total = 0
    product_ids = [_uuid(row.get("product_id")) for row in lines]
    products = {
        p.id: p
        for p in FoodProduct.objects.filter(
            tenant=tenant, pk__in=product_ids, is_active=True
        )
    }
    for row in lines:
        pid = _uuid(row.get("product_id"))
        product = products.get(pid)
        if product is None:
            raise FoodProductNotFoundError(
                f"Produto inexistente/inativo: {row.get('product_id')}"
            )
        qty = Decimal(str(row.get("quantity", 0)))
        if qty <= 0:
            raise FoodInvalidOrderError("Quantidade da compra deve ser > 0.")
        unit_cost = int(row.get("unit_cost_cents", product.cost_cents or 0))
        if unit_cost < 0:
            raise FoodInvalidOrderError("Custo unitário inválido.")
        line_total = int((Decimal(unit_cost) * qty).quantize(Decimal("1")))
        prepared.append((product, qty, unit_cost, line_total))
        total += line_total

    try:
        with transaction.atomic():
            purchase = FoodPurchase.objects.create(
                tenant=tenant,
                supplier=supplier,
                status=(
                    FoodPurchase.Status.ORDERED
                    if mark_ordered
                    else FoodPurchase.Status.DRAFT
                ),
                idempotency_key=key,
                expected_at=expected_at,
                notes=notes or "",
                total_cents=total,
            )
            for product, qty, unit_cost, line_total in prepared:
                FoodPurchaseLine.objects.create(
                    tenant=tenant,
                    purchase=purchase,
                    product=product,
                    quantity=qty,
                    unit_cost_cents=unit_cost,
                    line_total_cents=line_total,
                )
    except IntegrityError as exc:
        again = FoodPurchase.objects.filter(tenant=tenant, idempotency_key=key).first()
        if again is not None:
            return again
        raise FoodInvalidOrderError("Conflito de idempotência na compra.") from exc
    return purchase


def receive_purchase(*, tenant, purchase_id) -> FoodPurchase:
    """Baixa entrada de estoque e marca compra como recebida."""
    with transaction.atomic():
        purchase = (
            FoodPurchase.objects.select_for_update()
            .filter(tenant=tenant, pk=purchase_id)
            .first()
        )
        if purchase is None:
            raise FoodInvalidOrderError("Compra não encontrada.")
        if purchase.status == FoodPurchase.Status.RECEIVED:
            return purchase
        if purchase.status == FoodPurchase.Status.CANCELLED:
            raise FoodInvalidTransitionError("Compra cancelada.")
        if purchase.status not in {
            FoodPurchase.Status.DRAFT,
            FoodPurchase.Status.ORDERED,
        }:
            raise FoodInvalidTransitionError(
                f"Não é possível receber compra em status {purchase.status}."
            )
        for line in purchase.lines.select_related("product"):
            apply_stock_movement(
                tenant=tenant,
                product=line.product,
                movement_type=FoodStockMovement.MovementType.IN,
                quantity=line.quantity,
                reason=f"compra:{purchase.id}",
            )
            if line.unit_cost_cents > 0 and line.product.cost_cents != line.unit_cost_cents:
                line.product.cost_cents = line.unit_cost_cents
                line.product.save(update_fields=["cost_cents", "updated_at"])
        purchase.status = FoodPurchase.Status.RECEIVED
        purchase.received_at = timezone.now()
        purchase.save(update_fields=["status", "received_at", "updated_at"])
    return purchase


def transition_order_status(*, tenant, order_id, to_status: str) -> FoodOrder:
    order = FoodOrder.objects.filter(tenant=tenant, pk=order_id).first()
    if order is None:
        raise FoodOrderNotFoundError("Pedido não encontrado.")
    allowed = ORDER_TRANSITIONS.get(order.status, set())
    if to_status not in allowed:
        raise FoodInvalidTransitionError(
            f"Transição inválida: {order.status} → {to_status}."
        )
    order.status = to_status
    order.save(update_fields=["status", "updated_at"])
    return order


def create_delivery_route(
    *,
    tenant,
    name: str,
    service_date: date,
    driver_name: str = "",
) -> FoodDeliveryRoute:
    name = (name or "").strip() or f"Rota {service_date}"
    return FoodDeliveryRoute.objects.create(
        tenant=tenant,
        name=name,
        service_date=service_date,
        driver_name=(driver_name or "").strip(),
    )


def assign_order_to_route(
    *,
    tenant,
    route_id,
    order_id,
    sequence: int | None = None,
) -> FoodDeliveryStop:
    route = FoodDeliveryRoute.objects.filter(tenant=tenant, pk=route_id).first()
    if route is None:
        raise FoodInvalidOrderError("Rota não encontrada.")
    if route.status == FoodDeliveryRoute.Status.CLOSED:
        raise FoodInvalidTransitionError("Rota fechada.")
    order = FoodOrder.objects.filter(tenant=tenant, pk=order_id).first()
    if order is None:
        raise FoodOrderNotFoundError("Pedido não encontrado.")
    if order.status in {FoodOrder.Status.CANCELLED, FoodOrder.Status.DRAFT}:
        raise FoodInvalidOrderError("Pedido não elegível para delivery.")
    if FoodDeliveryStop.objects.filter(order=order).exists():
        return FoodDeliveryStop.objects.get(order=order)
    if sequence is None:
        last = (
            FoodDeliveryStop.objects.filter(tenant=tenant, route=route)
            .order_by("-sequence")
            .first()
        )
        sequence = (last.sequence + 1) if last else 1

    stop = FoodDeliveryStop.objects.create(
        tenant=tenant,
        route=route,
        order=order,
        sequence=sequence,
        status=FoodDeliveryStop.Status.PENDING,
    )
    if order.fulfillment_mode != FoodOrder.FulfillmentMode.DELIVERY:
        order.fulfillment_mode = FoodOrder.FulfillmentMode.DELIVERY
        order.save(update_fields=["fulfillment_mode", "updated_at"])
    if route.status == FoodDeliveryRoute.Status.OPEN:
        route.status = FoodDeliveryRoute.Status.IN_PROGRESS
        route.save(update_fields=["status", "updated_at"])
    return stop


def update_delivery_stop_status(
    *, tenant, stop_id, to_status: str
) -> FoodDeliveryStop:
    stop = (
        FoodDeliveryStop.objects.select_related("order")
        .filter(tenant=tenant, pk=stop_id)
        .first()
    )
    if stop is None:
        raise FoodInvalidOrderError("Parada não encontrada.")
    allowed = {
        FoodDeliveryStop.Status.PENDING: {
            FoodDeliveryStop.Status.OUT,
            FoodDeliveryStop.Status.FAILED,
        },
        FoodDeliveryStop.Status.OUT: {
            FoodDeliveryStop.Status.DELIVERED,
            FoodDeliveryStop.Status.FAILED,
        },
    }
    if to_status not in allowed.get(stop.status, set()):
        raise FoodInvalidTransitionError(
            f"Parada: {stop.status} → {to_status} inválido."
        )
    stop.status = to_status
    fields = ["status", "updated_at"]
    if to_status == FoodDeliveryStop.Status.DELIVERED:
        stop.delivered_at = timezone.now()
        fields.append("delivered_at")
        if stop.order.status not in {
            FoodOrder.Status.FULFILLED,
            FoodOrder.Status.CANCELLED,
        }:
            stop.order.status = FoodOrder.Status.FULFILLED
            stop.order.save(update_fields=["status", "updated_at"])
    stop.save(update_fields=fields)
    return stop


def upsert_marketplace_connection(
    *,
    tenant,
    provider: str,
    merchant_ref: str,
    is_active: bool = True,
    settings: dict | None = None,
) -> FoodMarketplaceConnection:
    if provider not in FoodMarketplaceConnection.Provider.values:
        raise FoodInvalidOrderError(f"Provider marketplace inválido: {provider}")
    merchant_ref = (merchant_ref or "").strip()
    if not merchant_ref:
        raise FoodInvalidOrderError("merchant_ref é obrigatório.")
    conn, _ = FoodMarketplaceConnection.objects.update_or_create(
        tenant=tenant,
        provider=provider,
        merchant_ref=merchant_ref,
        defaults={
            "is_active": is_active,
            "settings": settings or {},
        },
    )
    return conn


def import_marketplace_order(
    *,
    tenant,
    provider: str,
    external_order_id: str,
    customer_name: str,
    customer_phone: str = "",
    lines: list[dict[str, Any]],
    total_cents: int | None = None,
    delivery_address: str = "",
    merchant_ref: str = "",
    paid: bool = True,
) -> FoodOrder:
    """
    Ingere pedido de iFood/aiqfome no Order Service unificado.

    Não chama API externa (stub/ingress). Idempotente por
    `mp:{provider}:{external_order_id}`.
    """
    if provider not in (
        FoodOrder.Channel.IFOOD,
        FoodOrder.Channel.AIQFOME,
    ):
        raise FoodInvalidOrderError(f"Canal marketplace inválido: {provider}")
    ext = (external_order_id or "").strip()
    if not ext:
        raise FoodInvalidOrderError("external_order_id é obrigatório.")

    idem = f"mp:{provider}:{ext}"
    existing = FoodOrder.objects.filter(tenant=tenant, idempotency_key=idem).first()
    if existing is not None:
        return existing

    conn = None
    if merchant_ref:
        conn = FoodMarketplaceConnection.objects.filter(
            tenant=tenant, provider=provider, merchant_ref=merchant_ref
        ).first()
        if conn is None:
            conn = upsert_marketplace_connection(
                tenant=tenant, provider=provider, merchant_ref=merchant_ref
            )

    phone = (customer_phone or "").strip()
    customer = None
    if phone:
        customer = FoodCustomer.objects.filter(
            tenant=tenant, phone_e164=phone
        ).first()
    if customer is None:
        customer = create_food_customer(
            tenant=tenant,
            name=(customer_name or "Cliente marketplace").strip(),
            phone_e164=phone,
        )

    order_lines = []
    for row in lines:
        product_id = row.get("product_id")
        if not product_id:
            sku = (row.get("sku") or "").strip()
            product = FoodProduct.objects.filter(
                tenant=tenant, sku=sku, is_active=True
            ).first()
            if product is None:
                raise FoodProductNotFoundError(
                    f"SKU não cadastrado para import marketplace: {sku}"
                )
            product_id = product.id
        order_lines.append(
            {
                "product_id": product_id,
                "quantity": row.get("quantity", 1),
                "unit_price_cents": row.get("unit_price_cents"),
            }
        )

    order = create_order(
        tenant=tenant,
        customer_id=customer.id,
        channel=provider,
        lines=order_lines,
        idempotency_key=idem,
        notes=f"Import {provider} #{ext}",
        await_pix=not paid,
        deduct_stock=False,
    )
    # Idempotência do create_order pode retornar pedido já existente sem flags marketplace
    update_fields = []
    if order.channel_ref != ext:
        order.channel_ref = ext
        update_fields.append("channel_ref")
    if delivery_address and order.delivery_address != delivery_address:
        order.delivery_address = delivery_address
        update_fields.append("delivery_address")
    if order.fulfillment_mode != FoodOrder.FulfillmentMode.DELIVERY:
        order.fulfillment_mode = FoodOrder.FulfillmentMode.DELIVERY
        update_fields.append("fulfillment_mode")
    if conn and order.marketplace_connection_id != conn.id:
        order.marketplace_connection = conn
        update_fields.append("marketplace_connection")
    if paid and order.payment_status != FoodOrder.PaymentStatus.PAID:
        # create_order com await_pix=False já marca paid; se total forçado, só status
        pass
    if update_fields:
        update_fields.append("updated_at")
        order.save(update_fields=update_fields)

    if total_cents is not None and total_cents >= 0 and order.total_cents != total_cents:
        # Respeita snapshot marketplace (taxa platform já embutida no total informado)
        order.total_cents = total_cents
        order.subtotal_cents = max(total_cents, order.subtotal_cents)
        order.save(update_fields=["total_cents", "subtotal_cents", "updated_at"])

    if paid and order.status == FoodOrder.Status.CONFIRMED:
        # pipeline operacional: marketplace já pago → preparar
        try:
            order = transition_order_status(
                tenant=tenant,
                order_id=order.id,
                to_status=FoodOrder.Status.PREPARING,
            )
        except FoodInvalidTransitionError:
            pass
    return order


def sync_marketplace_connection(
    *,
    tenant,
    connection: FoodMarketplaceConnection | None = None,
    connection_id=None,
    session=None,
) -> dict[str, Any]:
    """
    Puxa pedidos via HTTP (ou stub) e importa no Order Service unificado.
    Retorna contadores: fetched, imported, skipped, errors.
    """
    from integrations.marketplace.errors import MarketplaceError
    from integrations.marketplace.factory import build_marketplace_gateway
    from integrations.marketplace.normalize import normalize_marketplace_order

    if connection is None:
        if connection_id is None:
            raise FoodInvalidOrderError("connection ou connection_id obrigatório.")
        connection = FoodMarketplaceConnection.objects.filter(
            tenant=tenant, pk=connection_id
        ).first()
        if connection is None:
            raise FoodInvalidOrderError("Conexão marketplace não encontrada.")

    if not connection.is_active:
        raise FoodInvalidOrderError("Conexão marketplace inativa.")

    result: dict[str, Any] = {
        "connection_id": str(connection.id),
        "provider": connection.provider,
        "merchant_ref": connection.merchant_ref,
        "fetched": 0,
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "order_ids": [],
    }
    try:
        gateway = build_marketplace_gateway(
            provider=connection.provider,
            conn_settings=connection.settings or {},
            session=session,
        )
        raw_orders = gateway.fetch_orders(merchant_ref=connection.merchant_ref)
    except MarketplaceError as exc:
        result["errors"].append({"message": str(exc), "code": exc.code})
        return result
    except Exception as exc:  # pragma: no cover - rede
        result["errors"].append({"message": str(exc), "code": "marketplace_error"})
        return result

    result["fetched"] = len(raw_orders)
    sku_map = (connection.settings or {}).get("sku_map") or {}
    if not isinstance(sku_map, dict):
        sku_map = {}

    for raw in raw_orders:
        if not isinstance(raw, dict):
            result["errors"].append({"message": "pedido bruto inválido"})
            continue
        try:
            payload = normalize_marketplace_order(
                provider=connection.provider,
                raw=raw,
                merchant_ref=connection.merchant_ref,
                sku_map={str(k): str(v) for k, v in sku_map.items()},
            )
            if not payload.get("external_order_id"):
                result["errors"].append({"message": "pedido sem id externo"})
                continue
            if not payload.get("lines"):
                result["errors"].append(
                    {
                        "external_order_id": payload.get("external_order_id"),
                        "message": "pedido sem lines",
                    }
                )
                continue
            idem = f"mp:{connection.provider}:{payload['external_order_id']}"
            existed = FoodOrder.objects.filter(
                tenant=tenant, idempotency_key=idem
            ).exists()
            order = import_marketplace_order(tenant=tenant, **payload)
            if existed:
                result["skipped"] += 1
            else:
                result["imported"] += 1
                result["order_ids"].append(str(order.id))
        except FoodError as exc:
            result["errors"].append(
                {
                    "message": str(exc),
                    "code": getattr(exc, "code", "food_error"),
                }
            )
        except Exception as exc:  # pragma: no cover
            result["errors"].append({"message": str(exc)})
    return result


def sync_all_marketplace_connections(*, tenant) -> list[dict[str, Any]]:
    conns = FoodMarketplaceConnection.objects.filter(tenant=tenant, is_active=True)
    return [
        sync_marketplace_connection(tenant=tenant, connection=c) for c in conns
    ]
