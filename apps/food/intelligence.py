"""Fase 4 — Inteligência commercial/fabril (heurísticas, sem ML opaco).

Métricas calculadas a partir de pedidos pagos e estoque. Não é modelo estatístico
bancado em batch — é previsível, testável e auditorável.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.food.models import (
    FoodBom,
    FoodCustomer,
    FoodOrder,
    FoodOrderLine,
    FoodProduct,
    FoodStockBalance,
)
from apps.food.production import explode_bom, mrp_suggestions


def _paid_lines_qs(*, tenant, since):
    return FoodOrderLine.objects.filter(
        tenant=tenant,
        order__payment_status=FoodOrder.PaymentStatus.PAID,
        order__paid_at__gte=since,
        product__isnull=False,
    ).select_related("product", "order")


def demand_forecast(
    *,
    tenant,
    lookback_days: int = 28,
    horizon_days: int = 7,
) -> list[dict[str, Any]]:
    """
    Previsão de demanda por SKU:
    - média diária de unidades vendidas no lookback
    - tendência linear simples (segunda metade vs primeira)
    - forecast_horizon = avg_daily * (1 + trend) * horizon_days
    """
    lookback_days = max(7, min(int(lookback_days), 180))
    horizon_days = max(1, min(int(horizon_days), 30))
    now = timezone.now()
    since = now - timedelta(days=lookback_days)
    mid = now - timedelta(days=lookback_days // 2)

    by_product: dict[Any, dict] = {}
    lines = _paid_lines_qs(tenant=tenant, since=since)
    for line in lines.iterator():
        pid = line.product_id
        bucket = by_product.setdefault(
            pid,
            {
                "product_id": str(pid),
                "sku": line.product.sku if line.product_id else "",
                "name": line.product.name if line.product_id else "",
                "qty_first_half": Decimal("0"),
                "qty_second_half": Decimal("0"),
                "qty_total": Decimal("0"),
                "revenue_cents": 0,
            },
        )
        qty = line.quantity
        paid_at = line.order.paid_at or line.order.created_at
        if paid_at and paid_at < mid:
            bucket["qty_first_half"] += qty
        else:
            bucket["qty_second_half"] += qty
        bucket["qty_total"] += qty
        bucket["revenue_cents"] += int(line.line_total_cents or 0)

    half_days = max(Decimal(lookback_days // 2), Decimal("1"))
    full_days = Decimal(lookback_days)
    out = []
    for data in by_product.values():
        avg_daily = data["qty_total"] / full_days
        rate1 = data["qty_first_half"] / half_days
        rate2 = data["qty_second_half"] / half_days
        if rate1 > 0:
            trend = float((rate2 - rate1) / rate1)
        elif rate2 > 0:
            trend = 1.0
        else:
            trend = 0.0
        # limita choques
        trend = max(-0.5, min(1.0, trend))
        forecast = avg_daily * Decimal(str(1 + trend)) * Decimal(horizon_days)
        forecast = max(Decimal("0"), forecast.quantize(Decimal("0.001")))
        out.append(
            {
                "product_id": data["product_id"],
                "sku": data["sku"],
                "name": data["name"],
                "units_sold_lookback": str(data["qty_total"].quantize(Decimal("0.001"))),
                "avg_daily_units": str(avg_daily.quantize(Decimal("0.0001"))),
                "trend_ratio": round(trend, 4),
                "forecast_units": str(forecast),
                "horizon_days": horizon_days,
                "lookback_days": lookback_days,
                "revenue_cents_lookback": data["revenue_cents"],
            }
        )
    out.sort(key=lambda r: Decimal(r["forecast_units"]), reverse=True)
    return out


def production_and_purchase_suggestions(
    *,
    tenant,
    lookback_days: int = 28,
    horizon_days: int = 7,
) -> dict[str, Any]:
    """
    Sugestões de produção (demanda + mínimo de estoque) e de compra de insumos.
    """
    demand = {d["product_id"]: d for d in demand_forecast(
        tenant=tenant, lookback_days=lookback_days, horizon_days=horizon_days
    )}
    mrp = mrp_suggestions(tenant=tenant)
    production: list[dict] = []
    seen = set()

    for row in mrp:
        pid = row["product_id"]
        seen.add(pid)
        fc = demand.get(pid)
        demand_qty = Decimal(fc["forecast_units"]) if fc else Decimal("0")
        mrp_qty = Decimal(row["suggested_qty"])
        suggested = max(mrp_qty, demand_qty)
        production.append(
            {
                **row,
                "forecast_units": str(demand_qty) if fc else "0",
                "suggested_qty": str(suggested.quantize(Decimal("0.001"))),
                "source": "mrp+demand" if fc else "mrp",
            }
        )

    # demanda de acabados com BOM sem estar no MRP (available ok mas forecast alto)
    for pid, fc in demand.items():
        if pid in seen:
            continue
        demand_qty = Decimal(fc["forecast_units"])
        if demand_qty <= 0:
            continue
        bom = FoodBom.objects.filter(
            tenant=tenant, product_id=pid, is_active=True
        ).first()
        if bom is None:
            continue
        bal = FoodStockBalance.objects.filter(product_id=pid).first()
        available = bal.available_quantity if bal else Decimal("0")
        gap = demand_qty - available
        if gap <= 0:
            continue
        shortages = []
        for comp in explode_bom(bom=bom, quantity=gap):
            cbal = FoodStockBalance.objects.filter(product_id=comp["product_id"]).first()
            cav = cbal.available_quantity if cbal else Decimal("0")
            if cav < comp["quantity"]:
                shortages.append(
                    {
                        "sku": comp["sku"],
                        "need": str(comp["quantity"]),
                        "available": str(cav),
                    }
                )
        production.append(
            {
                "product_id": pid,
                "sku": fc["sku"],
                "bom_id": str(bom.id),
                "available": str(available),
                "min_quantity": str(bal.min_quantity if bal else 0),
                "suggested_qty": str(gap.quantize(Decimal("0.001"))),
                "forecast_units": fc["forecast_units"],
                "component_shortages": shortages,
                "can_start": len(shortages) == 0,
                "source": "demand",
            }
        )

    purchase: dict[str, dict] = {}
    for sug in production:
        if not sug.get("bom_id"):
            continue
        bom = FoodBom.objects.filter(pk=sug["bom_id"]).first()
        if bom is None:
            continue
        for comp in explode_bom(bom=bom, quantity=Decimal(sug["suggested_qty"])):
            key = str(comp["product_id"])
            cbal = FoodStockBalance.objects.filter(product_id=comp["product_id"]).first()
            available = cbal.available_quantity if cbal else Decimal("0")
            min_q = cbal.min_quantity if cbal else Decimal("0")
            need = max(Decimal("0"), Decimal(comp["quantity"]) - available)
            if need <= 0 and available >= min_q:
                continue
            buy = max(need, min_q - available if min_q > available else need)
            if buy <= 0:
                continue
            cur = purchase.get(key)
            if cur is None or Decimal(cur["suggested_qty"]) < buy:
                purchase[key] = {
                    "product_id": key,
                    "sku": comp["sku"],
                    "suggested_qty": str(buy.quantize(Decimal("0.001"))),
                    "available": str(available),
                    "min_quantity": str(min_q),
                    "for_production_sku": sug["sku"],
                }

    return {
        "production": production,
        "purchase": list(purchase.values()),
        "horizon_days": horizon_days,
        "lookback_days": lookback_days,
    }


def customer_intelligence(*, tenant, inactive_days_default: int = 30) -> list[dict]:
    """
    Por cliente: churn risk, CLV, propensão de recompra (scores 0–100).
    """
    now = timezone.now()
    customers = FoodCustomer.objects.filter(tenant=tenant, is_active=True)
    result = []
    for c in customers.iterator():
        last = c.last_order_at or c.created_at
        days_since = (now - last).days if last else 999
        orders = max(int(c.order_count), 0)
        spent = int(c.total_spent_cents or 0)
        avg = int(c.avg_ticket_cents or 0) or (spent // orders if orders else 0)

        # frequência implícita: se tem orders, assume intervalo médio 30d / max(order,1) heurística
        if orders >= 2 and c.created_at:
            lifespan_days = max((now - c.created_at).days, 1)
            avg_interval = lifespan_days / max(orders - 1, 1)
        else:
            avg_interval = float(inactive_days_default)

        # churn: dias desde compra vs intervalo habitual
        if avg_interval <= 0:
            churn = 50
        else:
            ratio = days_since / avg_interval
            churn = int(min(100, max(0, (ratio - 0.8) * 50)))
            if days_since >= inactive_days_default * 2:
                churn = max(churn, 80)
            if days_since >= inactive_days_default and orders > 0:
                churn = max(churn, 55)

        # propensão recompra: recência baixa + frequência
        recency_score = max(0, 100 - min(100, days_since * 2))
        freq_score = min(100, orders * 15)
        propensity = int(0.6 * recency_score + 0.4 * freq_score)

        # CLV histórico + projeção simples 6 meses (propensity * avg * 3)
        expected_orders_6m = (propensity / 100.0) * 3.0
        projected = int(avg * expected_orders_6m)
        clv = spent + projected

        result.append(
            {
                "customer_id": str(c.id),
                "name": c.name,
                "phone_e164": c.phone_e164,
                "order_count": orders,
                "total_spent_cents": spent,
                "avg_ticket_cents": avg,
                "days_since_last_order": days_since,
                "churn_risk_score": churn,
                "repurchase_propensity_score": propensity,
                "clv_cents": clv,
                "clv_historical_cents": spent,
                "clv_projected_cents": projected,
            }
        )
    result.sort(key=lambda r: (-r["churn_risk_score"], -r["clv_cents"]))
    return result


def dynamic_pricing_suggestions(
    *,
    tenant,
    lookback_days: int = 28,
    max_uplift_bps: int = 1500,
    max_discount_bps: int = 1000,
) -> list[dict]:
    """
    Pricing dinâmico leve:
    - demanda alta + estoque baixo → sugere aumento (bps)
    - demanda baixa + estoque alto → sugere desconto
    Preço sugerido em centavos sobre price_cents atual (não grava automaticamente).
    """
    demand = {
        d["product_id"]: d
        for d in demand_forecast(tenant=tenant, lookback_days=lookback_days, horizon_days=7)
    }
    products = FoodProduct.objects.filter(tenant=tenant, is_active=True)
    out = []
    for p in products.iterator():
        bal = FoodStockBalance.objects.filter(product=p).first()
        available = float(bal.available_quantity) if bal else 0.0
        min_q = float(bal.min_quantity) if bal else 0.0
        fc = demand.get(str(p.id))
        forecast = float(fc["forecast_units"]) if fc else 0.0
        avg_daily = float(fc["avg_daily_units"]) if fc else 0.0
        price = int(p.price_cents or 0)
        cost = int(p.cost_cents or 0)
        if price <= 0:
            continue

        stock_ratio = available / forecast if forecast > 0 else (2.0 if available > 0 else 0.0)
        demand_pressure = avg_daily  # unidades/dia

        adjust_bps = 0
        reason = "stable"
        if forecast > 0 and available < forecast * 0.5:
            # escassez
            adjust_bps = min(max_uplift_bps, 500 + int(min(1000, demand_pressure * 100)))
            reason = "scarce_high_demand"
        elif min_q > 0 and available > min_q * 3 and forecast < max(min_q * 0.2, 1):
            adjust_bps = -min(max_discount_bps, 400 + int(available))
            reason = "overstock_low_demand"
        elif stock_ratio > 2.5 and demand_pressure < 0.2:
            adjust_bps = -min(max_discount_bps, 300)
            reason = "slow_mover"

        # não vende abaixo do custo
        suggested = price + (price * adjust_bps) // 10000
        if cost > 0:
            suggested = max(suggested, cost)
        if suggested < 0:
            suggested = price

        margin_bps = 0
        if suggested > 0 and cost >= 0:
            margin_bps = int(((suggested - cost) * 10000) / suggested)

        out.append(
            {
                "product_id": str(p.id),
                "sku": p.sku,
                "name": p.name,
                "price_cents": price,
                "cost_cents": cost,
                "available": str(bal.available_quantity if bal else 0),
                "forecast_units_7d": fc["forecast_units"] if fc else "0",
                "adjust_bps": adjust_bps,
                "suggested_price_cents": suggested,
                "margin_bps_at_suggested": margin_bps,
                "reason": reason,
            }
        )
    out.sort(key=lambda r: abs(r["adjust_bps"]), reverse=True)
    return out


def intelligence_report(
    *,
    tenant,
    lookback_days: int = 28,
    horizon_days: int = 7,
) -> dict[str, Any]:
    """Pacote completo Fase 4."""
    demand = demand_forecast(
        tenant=tenant, lookback_days=lookback_days, horizon_days=horizon_days
    )
    suggestions = production_and_purchase_suggestions(
        tenant=tenant, lookback_days=lookback_days, horizon_days=horizon_days
    )
    customers = customer_intelligence(tenant=tenant)
    pricing = dynamic_pricing_suggestions(tenant=tenant, lookback_days=lookback_days)

    high_churn = sum(1 for c in customers if c["churn_risk_score"] >= 70)
    return {
        "generated_at": timezone.now().isoformat(),
        "lookback_days": lookback_days,
        "horizon_days": horizon_days,
        "demand_forecast": demand[:50],
        "production_suggestions": suggestions["production"][:50],
        "purchase_suggestions": suggestions["purchase"][:50],
        "customer_intelligence": customers[:100],
        "pricing_suggestions": [p for p in pricing if p["adjust_bps"] != 0][:50],
        "summary": {
            "skus_with_demand": len(demand),
            "production_suggestions": len(suggestions["production"]),
            "purchase_suggestions": len(suggestions["purchase"]),
            "customers_scored": len(customers),
            "high_churn_customers": high_churn,
            "pricing_actions": sum(1 for p in pricing if p["adjust_bps"] != 0),
        },
    }
