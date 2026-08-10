"""Normaliza payloads iFood/aiqfome → kwargs de import_marketplace_order."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _money_to_cents(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        # se value > 1000 e inteiro sem ponto, assume centavos se flag; default: se < 10^4 pode ser reais
        # Convenção: int > 10000 tratado como centavos; senão se float-like em string;
        # Para int puro de APIs em centavos: preferimos key unit_price_cents
        return value
    try:
        d = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    # valores com casas decimais ou < 1000 típicos = reais
    if "." in str(value) or "," in str(value) or d < 1000:
        return int((d * 100).quantize(Decimal("1")))
    return int(d)


def _phone_e164(raw: str) -> str:
    s = "".join(c for c in (raw or "") if c.isdigit() or c == "+")
    if not s:
        return ""
    if s.startswith("+"):
        return s
    if s.startswith("55") and len(s) >= 12:
        return f"+{s}"
    if len(s) >= 10:
        return f"+55{s}"
    return s


def _resolve_sku(item: dict, sku_map: dict[str, str]) -> str:
    candidates = [
        item.get("sku"),
        item.get("externalCode"),
        item.get("external_code"),
        item.get("code"),
        item.get("ean"),
        str(item.get("id") or ""),
    ]
    for c in candidates:
        if not c:
            continue
        key = str(c).strip()
        if key in sku_map:
            return sku_map[key]
        if item.get("sku") and str(item.get("sku")).strip() == key:
            return key
    # map by name slug optional
    name = (item.get("name") or item.get("productName") or "").strip()
    if name and name in sku_map:
        return sku_map[name]
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    return ""


def normalize_marketplace_order(
    *,
    provider: str,
    raw: dict[str, Any],
    merchant_ref: str = "",
    sku_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Aceita:
    - envelope canônico EXEQ (usado no stub e testes)
    - shapes próximos de iFood Merchant API e aiqfome (campos comuns)
    """
    sku_map = sku_map or {}
    provider = (provider or "").strip().lower()

    # Canônico
    if raw.get("external_order_id") or (
        raw.get("lines") and isinstance(raw.get("lines"), list)
    ):
        lines_in = raw.get("lines") or []
        lines = []
        for row in lines_in:
            sku = (row.get("sku") or "").strip()
            if row.get("external_code") and sku:
                pass
            elif row.get("external_code") and not sku:
                sku = sku_map.get(str(row["external_code"]), str(row["external_code"]))
            lines.append(
                {
                    "sku": sku,
                    "product_id": row.get("product_id"),
                    "quantity": row.get("quantity", 1),
                    "unit_price_cents": row.get("unit_price_cents"),
                }
            )
        return {
            "provider": provider,
            "external_order_id": str(
                raw.get("external_order_id") or raw.get("id") or ""
            ),
            "customer_name": (raw.get("customer_name") or "Cliente marketplace").strip(),
            "customer_phone": _phone_e164(raw.get("customer_phone") or ""),
            "lines": lines,
            "total_cents": raw.get("total_cents"),
            "delivery_address": raw.get("delivery_address") or "",
            "merchant_ref": merchant_ref or raw.get("merchant_ref") or "",
            "paid": bool(raw.get("paid", True)),
        }

    # iFood-like / aiqfome-like
    oid = (
        raw.get("id")
        or raw.get("orderId")
        or raw.get("displayId")
        or raw.get("shortCode")
        or ""
    )
    customer = raw.get("customer") or raw.get("client") or {}
    if isinstance(customer, str):
        customer = {"name": customer}
    name = (
        customer.get("name")
        or customer.get("fullName")
        or raw.get("customerName")
        or "Cliente marketplace"
    )
    phone = (
        customer.get("phone")
        or customer.get("cellphone")
        or customer.get("mobileNumber")
        or ""
    )

    items = raw.get("items") or raw.get("products") or raw.get("orderItems") or []
    lines = []
    for item in items:
        sku = _resolve_sku(item, sku_map)
        price = item.get("unit_price_cents")
        if price is None:
            price = _money_to_cents(
                item.get("price")
                or item.get("unitPrice")
                or item.get("totalPrice")
                or item.get("value")
            )
        qty = item.get("quantity", item.get("qty", 1))
        lines.append(
            {
                "sku": sku,
                "quantity": qty,
                "unit_price_cents": price,
            }
        )

    total = raw.get("total_cents")
    if total is None:
        t = raw.get("total") or {}
        if isinstance(t, dict):
            total = _money_to_cents(
                t.get("orderAmount") or t.get("subTotal") or t.get("total")
            )
        else:
            total = _money_to_cents(t)

    delivery = raw.get("delivery") or raw.get("deliveryAddress") or {}
    address = raw.get("delivery_address") or ""
    if not address and isinstance(delivery, dict):
        addr = delivery.get("deliveryAddress") or delivery.get("address") or delivery
        if isinstance(addr, dict):
            address = (
                addr.get("formattedAddress")
                or addr.get("streetName")
                or addr.get("street")
                or ""
            )
            if addr.get("streetNumber"):
                address = f"{address}, {addr['streetNumber']}".strip(", ")
            if addr.get("neighborhood"):
                address = f"{address} - {addr['neighborhood']}"
        elif isinstance(addr, str):
            address = addr

    merchant = (
        merchant_ref
        or raw.get("merchant_ref")
        or (raw.get("merchant") or {}).get("id")
        or raw.get("storeId")
        or ""
    )

    payments = raw.get("payments") or raw.get("payment") or {}
    paid = True
    if isinstance(payments, dict) and payments.get("pending") is True:
        paid = False
    if raw.get("paid") is False:
        paid = False

    return {
        "provider": provider,
        "external_order_id": str(oid),
        "customer_name": str(name).strip() or "Cliente marketplace",
        "customer_phone": _phone_e164(str(phone)),
        "lines": lines,
        "total_cents": total,
        "delivery_address": address,
        "merchant_ref": str(merchant),
        "paid": paid,
    }
