"""RF-100 — catálogo NCM/CFOP/unidade (delega a apps.fiscal.goods_catalog)."""

from __future__ import annotations

from apps.fiscal.goods_catalog import (
    catalog_meta,
    catalog_version_label,
    validate_cfop_catalog,
    validate_ncm,
    validate_unit,
)
from apps.fiscal.goods_catalog_data import FALLBACK_VERSION

# Compat import-time (sem DB); em runtime preferir catalog_version_label().
CATALOG_VERSION = FALLBACK_VERSION

__all__ = [
    "CATALOG_VERSION",
    "catalog_meta",
    "catalog_version_label",
    "validate_cfop_catalog",
    "validate_ncm",
    "validate_unit",
]
