"""Campos prod XML NF-e/NFC-e — ADR-GOODS-VALIDATE-V1."""

from __future__ import annotations

from apps.fiscal.goods_validate import resolve_c_ean


def prod_c_ean(item: dict) -> str:
    return resolve_c_ean(item.get("gtin"))
