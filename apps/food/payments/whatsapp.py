"""Mensagens de pagamento Food para canal WhatsApp (contrato API)."""

from __future__ import annotations

from apps.food.models import FoodOrder
from apps.food.payments.services import get_active_food_payment

WHATSAPP_MESSAGE_MAX = 4096


def format_brl_cents(cents: int) -> str:
    value = cents / 100
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def resolve_pix_copy_paste(order: FoodOrder) -> str:
    payment = get_active_food_payment(order)
    if payment is not None and payment.pix_copy_paste:
        return payment.pix_copy_paste.strip()
    charge = getattr(order, "charge", None)
    if charge is not None and charge.pix_copy_paste:
        return (charge.pix_copy_paste or "").strip()
    return ""


def build_whatsapp_payment_message(order: FoodOrder) -> str:
    """
    Texto pronto para envio no WhatsApp após criar pedido + pagamento Pix.

    Não envia mensagem — apenas monta o conteúdo para o integrador (ex. apps/channel v1.1).
    """
    customer_name = ""
    if order.customer_id and getattr(order, "customer", None):
        customer_name = (order.customer.name or "").strip()
    greeting = f"Olá {customer_name}!" if customer_name else "Olá!"
    order_ref = str(order.id)[:8]
    total = format_brl_cents(order.total_cents)
    pix = resolve_pix_copy_paste(order)

    lines = [
        greeting,
        "",
        "Seu pedido EXEQ Food foi registrado.",
        f"Pedido: {order_ref}",
        f"Total: {total}",
    ]

    if order.payment_status == FoodOrder.PaymentStatus.PAID:
        lines.extend(["", "Pagamento já confirmado. Obrigado!"])
        return _fit_whatsapp_message("\n".join(lines))

    if pix:
        lines.extend(
            [
                "",
                "Pague via Pix Copia e Cola:",
                pix,
                "",
                "Após o pagamento, confirmamos automaticamente.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Estamos gerando seu Pix. Se não receber em instantes, "
                "consulte o pedido no Hub ou tente novamente.",
            ]
        )

    return _fit_whatsapp_message("\n".join(lines))


def build_whatsapp_order_paid_message(order: FoodOrder) -> str:
    """Mensagem curta após webhook confirmar pagamento (uso futuro channel)."""
    customer_name = ""
    if order.customer_id and getattr(order, "customer", None):
        customer_name = (order.customer.name or "").strip()
    greeting = f"Olá {customer_name}!" if customer_name else "Olá!"
    order_ref = str(order.id)[:8]
    return _fit_whatsapp_message(
        "\n".join(
            [
                greeting,
                "",
                f"Pagamento confirmado — pedido {order_ref}.",
                "Seu pedido já está em preparação.",
                "",
                "Obrigado pela preferência!",
            ]
        )
    )


def whatsapp_payment_payload(order: FoodOrder) -> dict:
    """Bloco estruturado para integradores (API / channel)."""
    pix = resolve_pix_copy_paste(order)
    return {
        "ready": bool(pix),
        "message": build_whatsapp_payment_message(order),
        "pix_copy_paste": pix,
        "order_id": str(order.id),
        "payment_status": order.payment_status,
    }


def _fit_whatsapp_message(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= WHATSAPP_MESSAGE_MAX:
        return text
    return text[: WHATSAPP_MESSAGE_MAX - 3] + "..."
