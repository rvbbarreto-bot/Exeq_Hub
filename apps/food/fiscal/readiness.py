"""Prontidão fiscal iFood — avisos informativos (PO-2: não bloqueia UI)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.accounts.tenant_emission import nfce_tenant_opt_in
from apps.food.fiscal.ident import resolve_food_order_customer_ident
from apps.food.models import FoodOrder
from apps.master_data.models import Provider
from apps.nfce.gate import build_gate_payload
from apps.nfce.services import nfce_feature_enabled


def resolve_emit_provider(*, tenant, order: FoodOrder) -> Provider | None:
    conn = order.marketplace_connection
    if conn:
        pid = (conn.settings or {}).get("provider_id")
        if pid:
            provider = Provider.objects.filter(
                tenant=tenant, pk=pid, is_active=True
            ).first()
            if provider is not None:
                return provider
    return Provider.objects.filter(tenant=tenant, is_active=True).order_by("created_at").first()


def assess_food_order_fiscal_readiness(order: FoodOrder) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    if order.channel != FoodOrder.Channel.IFOOD:
        return warnings

    if not nfce_feature_enabled():
        warnings.append(
            {
                "code": "nfce_disabled_global",
                "level": "error",
                "message": "NFC-e desabilitada globalmente (NFCE_ENABLED).",
            }
        )
    elif not nfce_tenant_opt_in(order.tenant):
        warnings.append(
            {
                "code": "nfce_disabled_tenant",
                "level": "error",
                "message": "NFC-e não habilitada para este tenant.",
            }
        )

    if order.fulfillment_mode == FoodOrder.FulfillmentMode.DELIVERY:
        cpf, cnpj = resolve_food_order_customer_ident(order)
        if not cpf and not cnpj:
            warnings.append(
                {
                    "code": "delivery_requires_identification",
                    "level": "warn",
                    "message": (
                        "Delivery sem CPF/CNPJ do cliente; emissão pode falhar na política NFC-e."
                    ),
                }
            )

    if order.status == FoodOrder.Status.CANCELLED:
        warnings.append(
            {
                "code": "order_logistic_cancelled",
                "level": "warn",
                "message": "Pedido cancelado no canal; emissão pode não fazer sentido.",
            }
        )

    if order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED:
        warnings.append(
            {
                "code": "already_authorized",
                "level": "info",
                "message": "NFC-e já autorizada para este pedido.",
            }
        )
    elif order.fiscal_status == FoodOrder.FiscalStatus.PROCESSING:
        warnings.append(
            {
                "code": "processing",
                "level": "info",
                "message": "Emissão fiscal em andamento.",
            }
        )
    elif order.fiscal_status == FoodOrder.FiscalStatus.IGNORED:
        warnings.append(
            {
                "code": "ignored",
                "level": "info",
                "message": "Pedido marcado como ignorado para emissão.",
            }
        )

    if order.fiscal_status == FoodOrder.FiscalStatus.AUTHORIZED and (
        order.status == FoodOrder.Status.CANCELLED
    ):
        warnings.append(
            {
                "code": "marketplace_cancelled_with_nfce",
                "level": "warn",
                "message": (
                    "Pedido cancelado no iFood com NFC-e autorizada; "
                    "cancele a NFC-e manualmente no Hub."
                ),
            }
        )

    provider = resolve_emit_provider(tenant=order.tenant, order=order)
    if provider is None:
        warnings.append(
            {
                "code": "no_provider",
                "level": "error",
                "message": "Nenhum emitente ativo cadastrado.",
            }
        )
    else:
        gate = build_gate_payload(tenant=order.tenant, provider_id=str(provider.id))
        for check in gate.get("checks") or []:
            if check.get("must") and not check.get("ok"):
                warnings.append(
                    {
                        "code": f"gate_{check.get('id', 'unknown')}",
                        "level": "error",
                        "message": str(check.get("label") or "Gate NFC-e"),
                    }
                )

    lines = list(order.lines.select_related("product", "product__nfe_product"))
    if not lines:
        warnings.append(
            {
                "code": "no_lines",
                "level": "error",
                "message": "Pedido sem itens.",
            }
        )
    for line in lines:
        if line.product is None:
            warnings.append(
                {
                    "code": "line_product_missing",
                    "level": "error",
                    "message": f"Item {line.sku}: produto Food ausente.",
                    "sku": line.sku,
                }
            )
            continue
        nfe = line.product.nfe_product
        if nfe is None:
            warnings.append(
                {
                    "code": "nfe_product_unmapped",
                    "level": "error",
                    "message": f"SKU {line.sku}: produto fiscal não mapeado.",
                    "sku": line.sku,
                }
            )
        elif not nfe.is_active:
            warnings.append(
                {
                    "code": "nfe_product_inactive",
                    "level": "error",
                    "message": f"SKU {line.sku}: produto fiscal inativo.",
                    "sku": line.sku,
                }
            )

    mode = (getattr(settings, "NFCE_HTTP_MODE", "stub") or "stub").lower()
    if mode not in {"stub", "http"}:
        warnings.append(
            {
                "code": "nfce_http_mode",
                "level": "warn",
                "message": f"Modo NFC-e HTTP={mode!r} não reconhecido.",
            }
        )

    return warnings


def refresh_food_order_fiscal_state(order: FoodOrder) -> FoodOrder:
    if order.channel != FoodOrder.Channel.IFOOD:
        return order

    update_fields = ["fiscal_warnings", "updated_at"]
    if not order.fiscal_status:
        order.fiscal_status = FoodOrder.FiscalStatus.PENDING
        update_fields.append("fiscal_status")

    order.fiscal_warnings = assess_food_order_fiscal_readiness(order)
    order.save(update_fields=update_fields)
    return order
