"""Parse de formulários Hub Food."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.http import QueryDict


def parse_order_lines(post: QueryDict) -> list[dict]:
    """Extrai linhas de pedido (multi-item) do POST Hub."""
    product_ids = post.getlist("line_product_id")
    quantities = post.getlist("line_quantity")
    if not product_ids:
        legacy_pid = (post.get("product_id") or "").strip()
        legacy_qty = (post.get("quantity") or "1").strip()
        if legacy_pid:
            product_ids = [legacy_pid]
            quantities = [legacy_qty]
    if len(product_ids) != len(quantities):
        raise ValueError("Linhas do pedido inconsistentes.")
    lines: list[dict] = []
    for product_id, raw_qty in zip(product_ids, quantities):
        pid = (product_id or "").strip()
        if not pid:
            continue
        raw = (raw_qty or "1").strip().replace(",", ".")
        try:
            qty = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("Quantidade inválida em uma das linhas.") from exc
        if qty <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")
        lines.append({"product_id": pid, "quantity": qty})
    if not lines:
        raise ValueError("Informe ao menos um produto no pedido.")
    return lines
