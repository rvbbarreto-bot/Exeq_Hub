"""Helpers Hub NFC-e Avulsa (PDV) — parse form, pagamentos tPag."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.http import QueryDict

from apps.nfe.models import NfeProduct

# tPag SEFAZ — MVP PO (01/17/03/99)
NFCE_PDV_PAYMENT_METHODS: tuple[tuple[str, str], ...] = (
    ("01", "Dinheiro"),
    ("17", "Pix"),
    ("03", "Cartão crédito"),
    ("99", "Outros"),
)

_ALLOWED_TPAG = frozenset(code for code, _ in NFCE_PDV_PAYMENT_METHODS)


def parse_unit_price_cents(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def parse_nfce_pdv_lines(post: QueryDict, *, tenant) -> list[dict[str, Any]]:
    """POST arrays line_product_id / line_quantity / line_unit_price."""
    product_ids = post.getlist("line_product_id")
    quantities = post.getlist("line_quantity")
    prices = post.getlist("line_unit_price")
    if not product_ids:
        legacy_id = (post.get("product_id") or "").strip()
        if legacy_id:
            product_ids = [legacy_id]
            quantities = [post.get("quantity") or "1"]
            prices = [post.get("unit_price") or ""]

    items: list[dict[str, Any]] = []
    for idx, pid in enumerate(product_ids):
        pid = (pid or "").strip()
        if not pid:
            continue
        if not NfeProduct.objects.filter(tenant=tenant, pk=pid, is_active=True).exists():
            raise ValueError(f"Produto inválido ou inativo: {pid}")
        qty = (quantities[idx] if idx < len(quantities) else "1") or "1"
        if Decimal(str(qty).replace(",", ".")) <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")
        item: dict[str, Any] = {"product_id": pid, "quantity": str(qty).replace(",", ".")}
        if idx < len(prices):
            cents = parse_unit_price_cents(prices[idx])
            if cents is not None:
                item["unit_price_cents"] = cents
        items.append(item)

    if not items:
        raise ValueError("Adicione ao menos um produto do catálogo fiscal.")
    return items


def parse_payment_method(post: QueryDict) -> str:
    code = (post.get("payment_method") or "99").strip()
    if code not in _ALLOWED_TPAG:
        raise ValueError("Forma de pagamento inválida.")
    return code
