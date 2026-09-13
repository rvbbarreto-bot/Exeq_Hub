"""Adapter Food → billing.Charge (Inter / Asaas / C6) sem alterar apps/billing."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.billing.amount_rules import CHARGE_MIN_AMOUNT_CENTS
from apps.billing.due_date_rules import min_due_date
from apps.billing.exceptions import GatewayRegistrationError, InvalidChargeInputError
from apps.billing.services import create_charge
from apps.food.exceptions import (
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodOrderNotFoundError,
    FoodPaymentError,
    FoodPaymentProviderError,
)
from apps.food.models import FoodOrder, FoodPayment
from apps.food.payments.router import BILLING_CHARGE_PROVIDERS, resolve_food_payment_provider
from apps.food.services import ensure_fiscal_customer_for_food


class BillingChargeFoodPaymentProvider:
    """Emite cobrança via billing.Charge (fluxo legado Inter BolePix)."""

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
        if method != "pix":
            raise FoodPaymentProviderError(
                f"Provider {self.kind} Food suporta apenas Pix nesta versão."
            )
        food_kind = resolve_food_payment_provider(tenant=tenant)
        if food_kind in BILLING_CHARGE_PROVIDERS and food_kind != self.kind:
            raise FoodPaymentProviderError(
                f"Provider Food configurado ({food_kind}) diverge do adapter ({self.kind})."
            )
        billing_kind = str((getattr(tenant, "settings", None) or {}).get("payment_provider") or "inter").lower()
        if food_kind in BILLING_CHARGE_PROVIDERS and billing_kind != food_kind:
            raise FoodPaymentProviderError(
                f"food_payment_provider={food_kind} exige payment_provider={food_kind} "
                "no tenant (billing recorrente compartilha credenciais)."
            )

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
            return order

        existing_payment = (
            FoodPayment.objects.filter(
                tenant=tenant,
                order=order,
                provider=self.kind,
                method=FoodPayment.Method.PIX,
                status__in=[
                    FoodPayment.Status.PENDING,
                    FoodPayment.Status.AWAITING_PAYMENT,
                    FoodPayment.Status.PAID,
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if existing_payment is not None and existing_payment.charge_id:
            if order.charge_id != existing_payment.charge_id:
                order.charge = existing_payment.charge
                order.save(update_fields=["charge", "updated_at"])
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

        payment_key = f"food-order:{order.id}:pix"
        with transaction.atomic():
            payment, _ = FoodPayment.objects.get_or_create(
                tenant=tenant,
                idempotency_key=payment_key,
                defaults={
                    "order": order,
                    "provider": self.kind,
                    "method": FoodPayment.Method.PIX,
                    "status": FoodPayment.Status.AWAITING_PAYMENT,
                    "amount_cents": order.total_cents,
                    "pix_copy_paste": charge.pix_copy_paste or "",
                    "provider_payment_id": (charge.gateway_ref or "")[:128],
                    "gateway_payload": charge.gateway_payload,
                    "charge": charge,
                },
            )
            if payment.charge_id != charge.id:
                payment.charge = charge
                payment.pix_copy_paste = charge.pix_copy_paste or ""
                payment.provider_payment_id = (charge.gateway_ref or "")[:128]
                payment.save(
                    update_fields=[
                        "charge",
                        "pix_copy_paste",
                        "provider_payment_id",
                        "updated_at",
                    ]
                )

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
