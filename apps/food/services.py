"""Application services — EXEQ Hub Food (Sprint 1)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.food.exceptions import (
    FoodCustomerNotFoundError,
    FoodDuplicateIdempotencyError,
    FoodInsufficientStockError,
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodProductNotFoundError,
)
from apps.food.models import (
    FoodCustomer,
    FoodOrder,
    FoodOrderLine,
    FoodProduct,
    FoodStockBalance,
    FoodStockMovement,
)


def create_food_customer(
    *,
    tenant,
    name: str,
    phone_e164: str = "",
    email: str = "",
    document: str = "",
) -> FoodCustomer:
    name = (name or "").strip()
    if not name:
        raise FoodInvalidOrderError("Nome do cliente é obrigatório.")
    return FoodCustomer.objects.create(
        tenant=tenant,
        name=name,
        phone_e164=(phone_e164 or "").strip(),
        email=(email or "").strip(),
        document="".join(c for c in (document or "") if c.isdigit()),
    )


def create_food_product(
    *,
    tenant,
    sku: str,
    name: str,
    price_cents: int,
    cost_cents: int = 0,
    category: str = "",
    unit: str = "un",
    initial_stock: Decimal | int | str | None = None,
    min_quantity: Decimal | int | str = 0,
) -> FoodProduct:
    sku = (sku or "").strip()
    name = (name or "").strip()
    if not sku or not name:
        raise FoodInvalidOrderError("SKU e nome do produto são obrigatórios.")
    if price_cents < 0 or cost_cents < 0:
        raise FoodInvalidOrderError("Preço/custo não podem ser negativos.")
    with transaction.atomic():
        product = FoodProduct.objects.create(
            tenant=tenant,
            sku=sku,
            name=name,
            price_cents=price_cents,
            cost_cents=cost_cents,
            category=(category or "").strip(),
            unit=(unit or "un").strip() or "un",
        )
        qty = Decimal("0") if initial_stock is None else Decimal(str(initial_stock))
        FoodStockBalance.objects.create(
            tenant=tenant,
            product=product,
            quantity=qty,
            min_quantity=Decimal(str(min_quantity or 0)),
        )
        if qty > 0:
            FoodStockMovement.objects.create(
                tenant=tenant,
                product=product,
                movement_type=FoodStockMovement.MovementType.IN,
                quantity=qty,
                balance_after=qty,
                reason="saldo_inicial",
            )
    return product


def apply_stock_movement(
    *,
    tenant,
    product: FoodProduct,
    movement_type: str,
    quantity: Decimal | int | str,
    reason: str = "",
    order: FoodOrder | None = None,
    allow_negative: bool = False,
) -> FoodStockBalance:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise FoodInvalidOrderError("Quantidade do movimento deve ser > 0.")
    if product.tenant_id != tenant.id:
        raise FoodProductNotFoundError("Produto de outro tenant.")

    with transaction.atomic():
        balance, _ = FoodStockBalance.objects.select_for_update().get_or_create(
            product=product,
            defaults={
                "tenant": tenant,
                "quantity": Decimal("0"),
                "reserved_quantity": Decimal("0"),
                "min_quantity": Decimal("0"),
            },
        )
        current = balance.quantity
        reserved = balance.reserved_quantity
        available = current - reserved
        if movement_type == FoodStockMovement.MovementType.IN:
            new_qty = current + qty
            move_qty = qty
        elif movement_type == FoodStockMovement.MovementType.OUT:
            if qty > available and not allow_negative:
                raise FoodInsufficientStockError(
                    f"Estoque disponível insuficiente para {product.sku} "
                    f"(físico={current}, reservado={reserved}, pedido={qty})."
                )
            new_qty = current - qty
            if new_qty < 0 and not allow_negative:
                raise FoodInsufficientStockError(
                    f"Estoque insuficiente para {product.sku} "
                    f"(saldo={current}, pedido={qty})."
                )
            move_qty = qty
        elif movement_type == FoodStockMovement.MovementType.ADJUST:
            new_qty = qty
            move_qty = abs(new_qty - current) or Decimal("0.001")
        else:
            raise FoodInvalidOrderError(f"Tipo de movimento inválido: {movement_type}")

        if balance.reserved_quantity > new_qty and not allow_negative:
            # Ajuste/out não pode deixar físico < reservado
            if new_qty < balance.reserved_quantity:
                raise FoodInsufficientStockError(
                    f"Movimento deixaria físico ({new_qty}) abaixo do "
                    f"reservado ({balance.reserved_quantity}) em {product.sku}."
                )

        balance.quantity = new_qty
        balance.save(update_fields=["quantity", "updated_at"])
        FoodStockMovement.objects.create(
            tenant=tenant,
            product=product,
            movement_type=movement_type,
            quantity=move_qty,
            balance_after=new_qty,
            reason=reason or "",
            order=order,
        )
    return balance


def reserve_stock(
    *,
    tenant,
    product: FoodProduct,
    quantity: Decimal | int | str,
    reason: str = "",
) -> FoodStockBalance:
    """Reserva saldo disponível (não baixa físico)."""
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise FoodInvalidOrderError("Quantidade de reserva deve ser > 0.")
    with transaction.atomic():
        balance, _ = FoodStockBalance.objects.select_for_update().get_or_create(
            product=product,
            defaults={
                "tenant": tenant,
                "quantity": Decimal("0"),
                "reserved_quantity": Decimal("0"),
                "min_quantity": Decimal("0"),
            },
        )
        available = balance.quantity - balance.reserved_quantity
        if qty > available:
            raise FoodInsufficientStockError(
                f"Disponível insuficiente para reservar {product.sku} "
                f"(disp={available}, ped={qty})."
            )
        balance.reserved_quantity = balance.reserved_quantity + qty
        balance.save(update_fields=["reserved_quantity", "updated_at"])
    return balance


def release_stock_reservation(
    *,
    tenant,
    product: FoodProduct,
    quantity: Decimal | int | str,
) -> FoodStockBalance:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise FoodInvalidOrderError("Quantidade de liberação deve ser > 0.")
    with transaction.atomic():
        balance, _ = FoodStockBalance.objects.select_for_update().get_or_create(
            product=product,
            defaults={
                "tenant": tenant,
                "quantity": Decimal("0"),
                "reserved_quantity": Decimal("0"),
                "min_quantity": Decimal("0"),
            },
        )
        balance.reserved_quantity = max(
            Decimal("0"), balance.reserved_quantity - qty
        )
        balance.save(update_fields=["reserved_quantity", "updated_at"])
    return balance


def create_order(
    *,
    tenant,
    customer_id,
    channel: str,
    lines: list[dict[str, Any]],
    idempotency_key: str,
    notes: str = "",
    discount_cents: int = 0,
    coupon_code: str = "",
    await_pix: bool = True,
    deduct_stock: bool = False,
) -> FoodOrder:
    """
    Cria um pedido unificado (qualquer canal).

    - Idempotência por (tenant, idempotency_key).
    - Snapshot de preço/SKU nas linhas.
    - Status inicial: pending_payment + awaiting_pix (default) ou confirmed se não await_pix.
    - cupom rastreado: se coupon_code, calcula desconto e associa FoodCoupon.
    """
    from apps.food.retention import (
        quote_coupon_discount,
        redeem_coupon_for_order,
        stop_customer_enrollments,
    )

    key = (idempotency_key or "").strip()
    if not key:
        raise FoodInvalidOrderError("idempotency_key é obrigatória.")
    if discount_cents < 0:
        raise FoodInvalidOrderError("Desconto não pode ser negativo.")
    if channel not in FoodOrder.Channel.values:
        raise FoodInvalidOrderError(f"Canal inválido: {channel}")
    if not lines:
        raise FoodInvalidOrderError("Pedido precisa de ao menos uma linha.")

    existing = FoodOrder.objects.filter(tenant=tenant, idempotency_key=key).first()
    if existing is not None:
        return existing

    customer = FoodCustomer.objects.filter(tenant=tenant, pk=customer_id).first()
    if customer is None:
        raise FoodCustomerNotFoundError("Cliente Food não encontrado.")

    product_ids = [row.get("product_id") for row in lines]
    products = {
        p.id: p
        for p in FoodProduct.objects.filter(
            tenant=tenant, pk__in=product_ids, is_active=True
        )
    }

    prepared: list[tuple[FoodProduct, Decimal, int, int]] = []
    subtotal = 0
    for row in lines:
        pid = row.get("product_id")
        product = products.get(pid)
        if product is None:
            raise FoodProductNotFoundError(f"Produto inexistente/inativo: {pid}")
        qty = Decimal(str(row.get("quantity", 0)))
        if qty <= 0:
            raise FoodInvalidOrderError("Quantidade da linha deve ser > 0.")
        unit_price = row.get("unit_price_cents", product.price_cents)
        if unit_price is None:
            unit_price = product.price_cents
        unit_price = int(unit_price)
        if unit_price < 0:
            raise FoodInvalidOrderError("Preço unitário inválido.")
        line_total = int((Decimal(unit_price) * qty).quantize(Decimal("1")))
        prepared.append((product, qty, unit_price, line_total))
        subtotal += line_total

    coupon_obj = None
    code = (coupon_code or "").strip()
    if code:
        coupon_obj, discount_cents = quote_coupon_discount(
            tenant=tenant, code=code, subtotal_cents=subtotal
        )
    if discount_cents > subtotal:
        raise FoodInvalidOrderError("Desconto maior que o subtotal.")
    total = subtotal - discount_cents

    status = FoodOrder.Status.PENDING_PAYMENT
    payment_status = FoodOrder.PaymentStatus.AWAITING_PIX
    if not await_pix:
        status = FoodOrder.Status.CONFIRMED
        payment_status = FoodOrder.PaymentStatus.PAID

    try:
        with transaction.atomic():
            order = FoodOrder.objects.create(
                tenant=tenant,
                customer=customer,
                channel=channel,
                status=status,
                payment_status=payment_status,
                subtotal_cents=subtotal,
                discount_cents=discount_cents,
                total_cents=total,
                notes=notes or "",
                idempotency_key=key,
                coupon=coupon_obj,
                paid_at=timezone.now() if payment_status == FoodOrder.PaymentStatus.PAID else None,
            )
            for product, qty, unit_price, line_total in prepared:
                FoodOrderLine.objects.create(
                    tenant=tenant,
                    order=order,
                    product=product,
                    sku=product.sku,
                    name=product.name,
                    quantity=qty,
                    unit=product.unit,
                    unit_price_cents=unit_price,
                    line_total_cents=line_total,
                )
                if deduct_stock or payment_status == FoodOrder.PaymentStatus.PAID:
                    apply_stock_movement(
                        tenant=tenant,
                        product=product,
                        movement_type=FoodStockMovement.MovementType.OUT,
                        quantity=qty,
                        reason="venda",
                        order=order,
                    )
            if payment_status == FoodOrder.PaymentStatus.PAID:
                _bump_customer_metrics(customer, total_cents=total)
                redeem_coupon_for_order(order=order)
                stop_customer_enrollments(
                    tenant=tenant, customer=customer, reason="purchase"
                )
    except IntegrityError as exc:
        again = FoodOrder.objects.filter(tenant=tenant, idempotency_key=key).first()
        if again is not None:
            return again
        raise FoodDuplicateIdempotencyError("Conflito de idempotência no pedido.") from exc

    return order


def mark_order_paid_by_pix(
    *,
    tenant,
    order_id,
    pix_txid: str = "",
    deduct_stock: bool = True,
) -> FoodOrder:
    """Confirma pagamento (webhook banking / Charge.paid)."""
    from apps.food.exceptions import FoodOrderNotFoundError

    with transaction.atomic():
        order = (
            FoodOrder.objects.select_for_update()
            .filter(tenant=tenant, pk=order_id)
            .first()
        )
        if order is None:
            raise FoodOrderNotFoundError("Pedido não encontrado.")
        if order.payment_status == FoodOrder.PaymentStatus.PAID:
            return order
        if order.status == FoodOrder.Status.CANCELLED:
            raise FoodInvalidTransitionError("Pedido cancelado não pode ser pago.")
        if order.payment_status not in (
            FoodOrder.PaymentStatus.UNPAID,
            FoodOrder.PaymentStatus.AWAITING_PIX,
            FoodOrder.PaymentStatus.FAILED,
        ):
            raise FoodInvalidTransitionError(
                f"Transição de pagamento inválida: {order.payment_status}"
            )

        already_out = FoodStockMovement.objects.filter(
            tenant=tenant,
            order=order,
            movement_type=FoodStockMovement.MovementType.OUT,
        ).exists()
        if deduct_stock and not already_out:
            for line in order.lines.select_related("product"):
                if line.product_id is None:
                    continue
                apply_stock_movement(
                    tenant=tenant,
                    product=line.product,
                    movement_type=FoodStockMovement.MovementType.OUT,
                    quantity=line.quantity,
                    reason="venda_pix",
                    order=order,
                )

        order.payment_status = FoodOrder.PaymentStatus.PAID
        order.status = FoodOrder.Status.CONFIRMED
        if pix_txid:
            order.pix_txid = pix_txid.strip()
        order.paid_at = timezone.now()
        order.save(
            update_fields=[
                "payment_status",
                "status",
                "pix_txid",
                "paid_at",
                "updated_at",
            ]
        )
        _bump_customer_metrics(order.customer, total_cents=order.total_cents)
        from apps.food.retention import (
            redeem_coupon_for_order,
            stop_customer_enrollments,
        )

        redeem_coupon_for_order(order=order)
        stop_customer_enrollments(
            tenant=tenant, customer=order.customer, reason="purchase"
        )
    return order


def ensure_fiscal_customer_for_food(food_customer: FoodCustomer):
    """Bridge FoodCustomer → master_data.Customer (exigido por billing.Charge)."""
    from apps.master_data.models import Customer
    from apps.master_data.services import create_customer

    if food_customer.fiscal_customer_id:
        return food_customer.fiscal_customer

    digits = "".join(c for c in (food_customer.document or "") if c.isdigit())
    if len(digits) == 11:
        doc_type = Customer.DocumentType.CPF
    elif len(digits) == 14:
        doc_type = Customer.DocumentType.CNPJ
    else:
        raise FoodInvalidOrderError(
            "Cliente Food precisa de CPF (11) ou CNPJ (14) para emitir Pix."
        )

    existing = Customer.objects.filter(
        tenant_id=food_customer.tenant_id, document=digits
    ).first()
    if existing is not None:
        food_customer.fiscal_customer = existing
        food_customer.save(update_fields=["fiscal_customer", "updated_at"])
        return existing

    try:
        fiscal = create_customer(
            tenant=food_customer.tenant,
            document=digits,
            document_type=doc_type,
            name=food_customer.name,
            email=food_customer.email or "",
            whatsapp=food_customer.phone_e164 or "",
        )
    except Exception as exc:
        raise FoodInvalidOrderError(
            f"Não foi possível vincular tomador fiscal: {exc}"
        ) from exc

    food_customer.fiscal_customer = fiscal
    food_customer.save(update_fields=["fiscal_customer", "updated_at"])
    return fiscal


def create_pix_intent_for_order(*, tenant, order_id, due_date=None) -> FoodOrder:
    """
    Emite cobrança gateway (boleto+PIX) e associa ao pedido.
    Reusa apps.billing — sem segundo provider Pix.
    """
    from datetime import date

    from apps.billing.amount_rules import CHARGE_MIN_AMOUNT_CENTS
    from apps.billing.due_date_rules import min_due_date
    from apps.billing.exceptions import (
        GatewayRegistrationError,
        InvalidChargeInputError,
    )
    from apps.billing.services import create_charge
    from apps.food.exceptions import FoodOrderNotFoundError, FoodPaymentError

    order = (
        FoodOrder.objects.select_related("customer", "charge")
        .filter(tenant=tenant, pk=order_id)
        .first()
    )
    if order is None:
        raise FoodOrderNotFoundError("Pedido não encontrado.")
    if order.payment_status == FoodOrder.PaymentStatus.PAID:
        return order
    if order.status == FoodOrder.Status.CANCELLED:
        raise FoodInvalidTransitionError("Pedido cancelado.")
    if order.charge_id and order.charge is not None:
        # Já tem intent: devolve (idempotente)
        return order
    if order.total_cents < CHARGE_MIN_AMOUNT_CENTS:
        raise FoodInvalidOrderError(
            f"Valor do pedido abaixo do mínimo de cobrança "
            f"({CHARGE_MIN_AMOUNT_CENTS} centavos)."
        )

    fiscal = ensure_fiscal_customer_for_food(order.customer)
    due = due_date or min_due_date()
    charge_key = f"food-order:{order.id}"

    try:
        charge = create_charge(
            tenant=tenant,
            idempotency_key=charge_key,
            customer=fiscal,
            amount_cents=order.total_cents,
            due_date=due if isinstance(due, date) else min_due_date(),
            description=f"Pedido Food {order.id}",
        )
    except InvalidChargeInputError as exc:
        raise FoodInvalidOrderError(str(exc)) from exc
    except GatewayRegistrationError as exc:
        raise FoodPaymentError(str(exc)) from exc

    if isinstance(charge, list):
        charge = charge[0]

    order.charge = charge
    order.payment_status = FoodOrder.PaymentStatus.AWAITING_PIX
    if order.status == FoodOrder.Status.DRAFT:
        order.status = FoodOrder.Status.PENDING_PAYMENT
    order.pix_txid = (charge.gateway_ref or order.pix_txid or "")[:128]
    order.save(
        update_fields=[
            "charge",
            "payment_status",
            "status",
            "pix_txid",
            "updated_at",
        ]
    )
    return order


def sync_food_order_on_charge_paid(*, tenant, charge) -> FoodOrder | None:
    """Chamado após Charge → paid (webhook). Idempotente."""
    order = (
        FoodOrder.objects.filter(tenant=tenant, charge=charge)
        .order_by("created_at")
        .first()
    )
    if order is None:
        return None
    txid = (charge.gateway_ref or order.pix_txid or "")[:128]
    return mark_order_paid_by_pix(
        tenant=tenant,
        order_id=order.id,
        pix_txid=txid,
        deduct_stock=True,
    )


def _bump_customer_metrics(customer: FoodCustomer, *, total_cents: int) -> None:
    FoodCustomer.objects.filter(pk=customer.pk).update(
        order_count=F("order_count") + 1,
        total_spent_cents=F("total_spent_cents") + total_cents,
        last_order_at=timezone.now(),
    )
    customer.refresh_from_db()
    if customer.order_count > 0:
        customer.avg_ticket_cents = customer.total_spent_cents // customer.order_count
        customer.save(update_fields=["avg_ticket_cents", "updated_at"])
