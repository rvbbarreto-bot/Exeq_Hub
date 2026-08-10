"""Cupom rastreado + régua de retenção parametrizável (Food V1.1)."""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.food.exceptions import FoodInvalidOrderError
from apps.food.models import (
    FoodCampaign,
    FoodCoupon,
    FoodCouponRedemption,
    FoodCustomer,
    FoodOrder,
    FoodRetentionDispatch,
    FoodRetentionEnrollment,
    FoodRetentionRule,
    FoodRetentionStep,
)


def create_campaign(*, tenant, name: str, code: str, **extra) -> FoodCampaign:
    name = (name or "").strip()
    code = (code or "").strip().lower()
    if not name or not code:
        raise FoodInvalidOrderError("Campanha exige name e code.")
    return FoodCampaign.objects.create(tenant=tenant, name=name, code=code, **extra)


def create_coupon(
    *,
    tenant,
    code: str,
    discount_type: str,
    percent_bps: int = 0,
    amount_cents: int = 0,
    campaign: FoodCampaign | None = None,
    min_order_cents: int = 0,
    max_redemptions: int | None = None,
    valid_from=None,
    valid_until=None,
) -> FoodCoupon:
    code = (code or "").strip().upper()
    if not code:
        raise FoodInvalidOrderError("Código do cupom é obrigatório.")
    if discount_type == FoodCoupon.DiscountType.PERCENT:
        if percent_bps <= 0 or percent_bps > 10000:
            raise FoodInvalidOrderError("percent_bps deve ser 1..10000.")
    elif discount_type == FoodCoupon.DiscountType.FIXED:
        if amount_cents <= 0:
            raise FoodInvalidOrderError("amount_cents deve ser > 0.")
    else:
        raise FoodInvalidOrderError(f"discount_type inválido: {discount_type}")
    return FoodCoupon.objects.create(
        tenant=tenant,
        code=code,
        discount_type=discount_type,
        percent_bps=percent_bps,
        amount_cents=amount_cents,
        campaign=campaign,
        min_order_cents=min_order_cents,
        max_redemptions=max_redemptions,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def quote_coupon_discount(
    *, tenant, code: str, subtotal_cents: int
) -> tuple[FoodCoupon, int]:
    """Valida cupom e retorna (coupon, discount_cents)."""
    code = (code or "").strip().upper()
    if not code:
        raise FoodInvalidOrderError("Código de cupom vazio.")
    coupon = FoodCoupon.objects.filter(tenant=tenant, code=code).first()
    if coupon is None or not coupon.is_active:
        raise FoodInvalidOrderError("Cupom inválido ou inativo.")
    now = timezone.now()
    if coupon.valid_from and now < coupon.valid_from:
        raise FoodInvalidOrderError("Cupom ainda não válido.")
    if coupon.valid_until and now > coupon.valid_until:
        raise FoodInvalidOrderError("Cupom expirado.")
    if coupon.campaign_id:
        camp = coupon.campaign
        if camp and not camp.is_active:
            raise FoodInvalidOrderError("Campanha do cupom inativa.")
        if camp and camp.starts_at and now < camp.starts_at:
            raise FoodInvalidOrderError("Campanha ainda não iniciada.")
        if camp and camp.ends_at and now > camp.ends_at:
            raise FoodInvalidOrderError("Campanha encerrada.")
    if coupon.max_redemptions is not None and coupon.redemption_count >= coupon.max_redemptions:
        raise FoodInvalidOrderError("Cupom esgotado.")
    if subtotal_cents < coupon.min_order_cents:
        raise FoodInvalidOrderError(
            f"Pedido mínimo do cupom: {coupon.min_order_cents} centavos."
        )
    if coupon.discount_type == FoodCoupon.DiscountType.PERCENT:
        discount = (subtotal_cents * coupon.percent_bps) // 10000
    else:
        discount = min(int(coupon.amount_cents), subtotal_cents)
    if discount < 0:
        discount = 0
    if discount > subtotal_cents:
        discount = subtotal_cents
    return coupon, discount


def redeem_coupon_for_order(*, order: FoodOrder) -> FoodCouponRedemption | None:
    """Persiste resgate quando o pedido já está pago e tem cupom."""
    if not order.coupon_id:
        return None
    if order.payment_status != FoodOrder.PaymentStatus.PAID:
        return None
    existing = FoodCouponRedemption.objects.filter(order=order).first()
    if existing is not None:
        return existing
    coupon = order.coupon
    with transaction.atomic():
        locked = FoodCoupon.objects.select_for_update().get(pk=coupon.pk)
        if locked.max_redemptions is not None and locked.redemption_count >= locked.max_redemptions:
            raise FoodInvalidOrderError("Cupom esgotado no resgate.")
        redemption = FoodCouponRedemption.objects.create(
            tenant=order.tenant,
            coupon=locked,
            order=order,
            customer=order.customer,
            campaign=locked.campaign,
            discount_cents=order.discount_cents,
        )
        locked.redemption_count = locked.redemption_count + 1
        locked.save(update_fields=["redemption_count", "updated_at"])
    return redemption


def create_retention_rule(
    *,
    tenant,
    name: str,
    kind: str,
    steps: list[dict],
    inactivity_days: int = 30,
    min_order_count: int = 0,
    min_avg_ticket_cents: int = 0,
) -> FoodRetentionRule:
    """
    Cria régua + etapas.

    steps: [{sequence, delay_days, message_template, channel?, coupon_id?}, ...]
    """
    name = (name or "").strip()
    if not name:
        raise FoodInvalidOrderError("Nome da régua é obrigatório.")
    if kind not in FoodRetentionRule.Kind.values:
        raise FoodInvalidOrderError(f"kind inválido: {kind}")
    if not steps:
        raise FoodInvalidOrderError("Régua precisa de ao menos uma etapa.")
    with transaction.atomic():
        rule = FoodRetentionRule.objects.create(
            tenant=tenant,
            name=name,
            kind=kind,
            inactivity_days=inactivity_days,
            min_order_count=min_order_count,
            min_avg_ticket_cents=min_avg_ticket_cents,
        )
        for step in steps:
            seq = int(step["sequence"])
            FoodRetentionStep.objects.create(
                tenant=tenant,
                rule=rule,
                sequence=seq,
                delay_days=int(step.get("delay_days") or 0),
                channel=step.get("channel") or FoodRetentionStep.Channel.WHATSAPP,
                message_template=(step.get("message_template") or "").strip(),
                coupon_id=step.get("coupon_id"),
            )
    return rule


def stop_customer_enrollments(
    *, tenant, customer: FoodCustomer, reason: str = "purchase"
) -> int:
    """Ao comprar no meio da régua: interrompe todas as inscrições ativas."""
    now = timezone.now()
    return FoodRetentionEnrollment.objects.filter(
        tenant=tenant,
        customer=customer,
        status=FoodRetentionEnrollment.Status.ACTIVE,
    ).update(
        status=FoodRetentionEnrollment.Status.STOPPED,
        stopped_at=now,
        stop_reason=reason[:64],
        updated_at=now,
    )


def customer_matches_rule(customer: FoodCustomer, rule: FoodRetentionRule, *, now=None) -> bool:
    now = now or timezone.now()
    if not customer.is_active or not (customer.phone_e164 or "").strip():
        return False
    if rule.kind == FoodRetentionRule.Kind.INACTIVITY:
        anchor = customer.last_order_at or customer.created_at
        if anchor is None:
            return True
        return anchor <= now - timedelta(days=rule.inactivity_days)
    if rule.kind == FoodRetentionRule.Kind.VIP:
        return customer.order_count >= rule.min_order_count and rule.min_order_count > 0
    if rule.kind == FoodRetentionRule.Kind.HIGH_TICKET:
        return (
            customer.avg_ticket_cents >= rule.min_avg_ticket_cents
            and rule.min_avg_ticket_cents > 0
        )
    if rule.kind == FoodRetentionRule.Kind.CUSTOM:
        return True
    return False


def enroll_eligible_customers(*, tenant, rule: FoodRetentionRule | None = None) -> int:
    """Cria enrollments para clientes elegíveis ainda sem inscrição ativa na régua."""
    now = timezone.now()
    rules = FoodRetentionRule.objects.filter(tenant=tenant, is_active=True)
    if rule is not None:
        rules = rules.filter(pk=rule.pk)
    enrolled = 0
    for r in rules:
        first_step = r.steps.order_by("sequence").first()
        if first_step is None:
            continue
        active_ids = FoodRetentionEnrollment.objects.filter(
            tenant=tenant,
            rule=r,
            status=FoodRetentionEnrollment.Status.ACTIVE,
        ).values_list("customer_id", flat=True)
        qs = FoodCustomer.objects.filter(tenant=tenant, is_active=True).exclude(
            pk__in=active_ids
        )
        for customer in qs.iterator():
            if not customer_matches_rule(customer, r, now=now):
                continue
            FoodRetentionEnrollment.objects.create(
                tenant=tenant,
                rule=r,
                customer=customer,
                status=FoodRetentionEnrollment.Status.ACTIVE,
                next_sequence=first_step.sequence,
                enrolled_at=now,
                next_fire_at=now + timedelta(days=first_step.delay_days),
            )
            enrolled += 1
    return enrolled


def _render_message(template: str, *, customer: FoodCustomer, coupon: FoodCoupon | None) -> str:
    return (
        (template or "")
        .replace("{name}", customer.name or "")
        .replace("{coupon_code}", coupon.code if coupon else "")
    )


def fire_due_enrollments(*, tenant, limit: int = 200) -> int:
    """Dispara etapas vencidas com idempotência por enrollment+step."""
    from apps.channel.services import enqueue_notification

    now = timezone.now()
    due = (
        FoodRetentionEnrollment.objects.select_related("customer", "rule")
        .filter(
            tenant=tenant,
            status=FoodRetentionEnrollment.Status.ACTIVE,
            next_fire_at__lte=now,
        )
        .order_by("next_fire_at")[:limit]
    )
    fired = 0
    for enrollment in due:
        step = (
            FoodRetentionStep.objects.filter(
                tenant=tenant,
                rule=enrollment.rule,
                sequence=enrollment.next_sequence,
            )
            .select_related("coupon")
            .first()
        )
        if step is None:
            enrollment.status = FoodRetentionEnrollment.Status.COMPLETED
            enrollment.stopped_at = now
            enrollment.stop_reason = "no_more_steps"
            enrollment.save(
                update_fields=["status", "stopped_at", "stop_reason", "updated_at"]
            )
            continue

        idem = f"ret:{enrollment.id}:{step.sequence}"
        if FoodRetentionDispatch.objects.filter(
            tenant=tenant, idempotency_key=idem
        ).exists():
            # Já disparou: só avança ponteiro (recuperação)
            _advance_enrollment(enrollment, step, now)
            continue

        body = _render_message(
            step.message_template, customer=enrollment.customer, coupon=step.coupon
        )
        notification = None
        status = FoodRetentionDispatch.Status.SENT
        phone = (enrollment.customer.phone_e164 or "").strip()
        if not phone:
            status = FoodRetentionDispatch.Status.SKIPPED
            body = body or "(sem telefone)"
        else:
            try:
                notification = enqueue_notification(
                    tenant=tenant,
                    phone_e164=phone,
                    event_type=f"food.retention.{enrollment.rule.kind}",
                    message_body=body[:1000],
                )
            except Exception:
                status = FoodRetentionDispatch.Status.FAILED

        try:
            FoodRetentionDispatch.objects.create(
                tenant=tenant,
                enrollment=enrollment,
                step=step,
                idempotency_key=idem,
                status=status,
                message_body=body,
                channel_notification=notification,
                fired_at=now,
            )
        except IntegrityError:
            # corrida: outro worker
            pass
        else:
            if status == FoodRetentionDispatch.Status.SENT:
                fired += 1
            _advance_enrollment(enrollment, step, now)
    return fired


def _advance_enrollment(
    enrollment: FoodRetentionEnrollment, step: FoodRetentionStep, now
) -> None:
    next_step = (
        FoodRetentionStep.objects.filter(
            tenant=enrollment.tenant_id,
            rule=enrollment.rule,
            sequence__gt=step.sequence,
        )
        .order_by("sequence")
        .first()
    )
    if next_step is None:
        enrollment.status = FoodRetentionEnrollment.Status.COMPLETED
        enrollment.stopped_at = now
        enrollment.stop_reason = "completed"
        enrollment.save(
            update_fields=["status", "stopped_at", "stop_reason", "updated_at"]
        )
        return
    enrollment.next_sequence = next_step.sequence
    enrollment.next_fire_at = now + timedelta(days=next_step.delay_days)
    enrollment.save(update_fields=["next_sequence", "next_fire_at", "updated_at"])


def process_retention_tick(*, tenant, limit: int = 200) -> dict:
    """Enroll + fire — ponto único de job/cron."""
    enrolled = enroll_eligible_customers(tenant=tenant)
    fired = fire_due_enrollments(tenant=tenant, limit=limit)
    return {"enrolled": enrolled, "fired": fired}


def food_dashboard_metrics(*, tenant) -> dict:
    """KPIs leves do V1.1 (dashboard operacional)."""
    now = timezone.now()
    customers = FoodCustomer.objects.filter(tenant=tenant)
    active_customers = customers.filter(is_active=True).count()
    inactive_30 = customers.filter(
        Q(last_order_at__lte=now - timedelta(days=30))
        | Q(last_order_at__isnull=True, created_at__lte=now - timedelta(days=30))
    ).count()
    paid_orders = FoodOrder.objects.filter(
        tenant=tenant, payment_status=FoodOrder.PaymentStatus.PAID
    )
    sales = paid_orders.aggregate(
        revenue=Sum("total_cents"), count=Count("id"), avg=Sum("total_cents")
    )
    order_count = sales["count"] or 0
    revenue = sales["revenue"] or 0
    recovered = (
        FoodCouponRedemption.objects.filter(tenant=tenant).aggregate(
            s=Sum("discount_cents")
        )["s"]
        or 0
    )
    # receita dos pedidos com cupom = "recuperada/incentivada"
    coupon_revenue = (
        FoodOrder.objects.filter(
            tenant=tenant,
            payment_status=FoodOrder.PaymentStatus.PAID,
            coupon__isnull=False,
        ).aggregate(s=Sum("total_cents"))["s"]
        or 0
    )
    return {
        "customers_active": active_customers,
        "customers_inactive_30d": inactive_30,
        "orders_paid": order_count,
        "revenue_cents": revenue,
        "avg_ticket_cents": (revenue // order_count) if order_count else 0,
        "coupon_discount_cents": recovered,
        "coupon_orders_revenue_cents": coupon_revenue,
        "retention_active_enrollments": FoodRetentionEnrollment.objects.filter(
            tenant=tenant, status=FoodRetentionEnrollment.Status.ACTIVE
        ).count(),
    }
