"""Mercado Pago — adapter Food (Pix + cartão)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.food.exceptions import (
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodOrderNotFoundError,
    FoodPaymentCardTokenRequiredError,
    FoodPaymentEmailRequiredError,
    FoodPaymentMethodNotAllowedError,
)
from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.constants import FOOD_PAYMENT_MIN_AMOUNT_CENTS
from apps.food.payments.mercadopago.client import MercadoPagoClient
from apps.food.payments.mercadopago.payer import (
    normalize_document,
    payer_document_type,
    split_payer_name,
)
from apps.food.payments.router import PROVIDER_MERCADOPAGO, food_payment_methods_enabled


class MercadoPagoFoodPaymentProvider:
    kind: str

    def __init__(self, *, kind: str) -> None:
        self.kind = kind

    def create_payment_intent(
        self,
        *,
        tenant,
        order_id,
        method: str = "pix",
        due_date=None,
        card_token: str = "",
        payment_method_id: str = "",
        issuer_id: str = "",
        installments: int = 1,
    ) -> FoodOrder:
        method = (method or "pix").lower().strip()
        enabled = food_payment_methods_enabled(tenant=tenant)
        if method not in enabled:
            raise FoodPaymentMethodNotAllowedError(
                f"Método {method} não habilitado para o tenant."
            )

        order = (
            FoodOrder.objects.select_related("customer")
            .filter(tenant=tenant, pk=order_id)
            .first()
        )
        if order is None:
            raise FoodOrderNotFoundError("Pedido não encontrado.")
        if order.payment_status == FoodOrder.PaymentStatus.PAID:
            return order
        if order.status == FoodOrder.Status.CANCELLED:
            raise FoodInvalidTransitionError("Pedido cancelado.")

        payment_key = f"food-order:{order.id}:{method}"
        existing = FoodPayment.objects.filter(
            tenant=tenant,
            idempotency_key=payment_key,
        ).first()
        if existing is not None and existing.status in {
            FoodPayment.Status.PENDING,
            FoodPayment.Status.AWAITING_PAYMENT,
            FoodPayment.Status.PAID,
        }:
            return self._sync_order_from_payment(order=order, payment=existing)

        if order.total_cents < FOOD_PAYMENT_MIN_AMOUNT_CENTS:
            raise FoodInvalidOrderError(
                f"Valor do pedido abaixo do mínimo de pagamento "
                f"({FOOD_PAYMENT_MIN_AMOUNT_CENTS} centavos)."
            )

        payer = self._build_payer(order)
        external_reference = f"food-order:{order.id}"
        description = f"Pedido Food {order.id}"
        client = MercadoPagoClient(tenant=tenant)

        if method == "pix":
            result = client.create_pix_payment(
                amount_cents=order.total_cents,
                description=description,
                external_reference=external_reference,
                idempotency_key=payment_key,
                payer=payer,
            )
            mp_status = result.status
            pix_copy_paste = result.pix_copy_paste
            status_detail = ""
            raw = result.raw
            food_method = FoodPayment.Method.PIX
        elif method == "card":
            if not (card_token or "").strip():
                raise FoodPaymentCardTokenRequiredError(
                    "Token de cartão é obrigatório (Checkout Transparente Mercado Pago)."
                )
            result = client.create_card_payment(
                amount_cents=order.total_cents,
                description=description,
                external_reference=external_reference,
                idempotency_key=payment_key,
                payer=payer,
                token=card_token,
                payment_method_id=payment_method_id,
                issuer_id=issuer_id,
                installments=installments,
            )
            mp_status = result.status
            pix_copy_paste = ""
            status_detail = result.status_detail
            raw = result.raw
            food_method = FoodPayment.Method.CARD
        else:
            raise FoodPaymentMethodNotAllowedError(f"Método Mercado Pago inválido: {method}")

        payment_status = self._map_mp_status(mp_status)
        failure_detail = ""
        if payment_status == FoodPayment.Status.FAILED:
            failure_detail = status_detail or mp_status

        with transaction.atomic():
            if existing is not None and existing.status == FoodPayment.Status.FAILED:
                payment = existing
                payment.status = payment_status
                payment.provider_payment_id = result.payment_id[:128]
                payment.pix_copy_paste = pix_copy_paste
                payment.failure_detail = failure_detail[:255]
                payment.gateway_payload = raw
                if payment_status == FoodPayment.Status.PAID:
                    payment.paid_at = payment.paid_at or timezone.now()
                payment.save(
                    update_fields=[
                        "status",
                        "provider_payment_id",
                        "pix_copy_paste",
                        "failure_detail",
                        "gateway_payload",
                        "paid_at",
                        "updated_at",
                    ]
                )
            else:
                payment = FoodPayment.objects.create(
                    tenant=tenant,
                    order=order,
                    provider=PROVIDER_MERCADOPAGO,
                    method=food_method,
                    status=payment_status,
                    idempotency_key=payment_key,
                    provider_payment_id=result.payment_id[:128],
                    amount_cents=order.total_cents,
                    pix_copy_paste=pix_copy_paste,
                    failure_detail=failure_detail[:255],
                    gateway_payload=raw,
                    paid_at=(
                        timezone.now()
                        if payment_status == FoodPayment.Status.PAID
                        else None
                    ),
                )
            order = self._sync_order_from_payment(order=order, payment=payment)
        return order

    def _build_payer(self, order: FoodOrder) -> dict:
        customer = order.customer
        email = (customer.email or "").strip()
        if not email:
            raise FoodPaymentEmailRequiredError(
                "E-mail do cliente é obrigatório para pagamento Mercado Pago."
            )
        digits = normalize_document(customer.document)
        if len(digits) not in (11, 14):
            raise FoodInvalidOrderError(
                "Cliente Food precisa de CPF (11) ou CNPJ (14) para pagamento Mercado Pago."
            )
        first_name, last_name = split_payer_name(customer.name)
        return {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "identification": {
                "type": payer_document_type(digits),
                "number": digits,
            },
        }

    def _map_mp_status(self, mp_status: str) -> str:
        raw = (mp_status or "pending").lower()
        if raw in {"approved", "accredited"}:
            return FoodPayment.Status.PAID
        if raw in {"rejected", "refunded", "charged_back"}:
            return FoodPayment.Status.FAILED
        if raw in {"cancelled", "canceled"}:
            return FoodPayment.Status.CANCELLED
        return FoodPayment.Status.AWAITING_PAYMENT

    def _sync_order_from_payment(
        self, *, order: FoodOrder, payment: FoodPayment
    ) -> FoodOrder:
        if payment.status == FoodPayment.Status.PAID:
            from apps.food.services import mark_order_paid

            return mark_order_paid(
                tenant=order.tenant,
                order_id=order.id,
                provider_ref=payment.provider_payment_id,
                deduct_stock=True,
            )

        if payment.status == FoodPayment.Status.FAILED:
            order.payment_status = FoodOrder.PaymentStatus.FAILED
            order.save(update_fields=["payment_status", "updated_at"])
            return order

        order.payment_status = FoodOrder.PaymentStatus.AWAITING_PAYMENT
        if order.status == FoodOrder.Status.DRAFT:
            order.status = FoodOrder.Status.PENDING_PAYMENT
        order.pix_txid = (payment.provider_payment_id or order.pix_txid or "")[:128]
        order.save(
            update_fields=[
                "payment_status",
                "status",
                "pix_txid",
                "updated_at",
            ]
        )
        return order
