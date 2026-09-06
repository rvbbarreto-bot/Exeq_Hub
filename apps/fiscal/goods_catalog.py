"""Catálogo mercadorias versionado — resolver, validação e dropdowns Hub."""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.fiscal.goods_catalog_data import (
    CFOP_ITEMS,
    FALLBACK_VERSION,
    NCM_ITEMS,
    UNIT_ITEMS,
)
from apps.fiscal.models import GoodsCatalogItem, GoodsCatalogVersion


def _fallback_ncm() -> frozenset[str]:
    return frozenset(code for code, _ in NCM_ITEMS)


def _fallback_cfop() -> frozenset[str]:
    return frozenset(code for code, _, _ in CFOP_ITEMS)


def _fallback_units() -> frozenset[str]:
    return frozenset(code for code, _ in UNIT_ITEMS)


def get_published_version() -> GoodsCatalogVersion | None:
    try:
        return (
            GoodsCatalogVersion.objects.filter(status=GoodsCatalogVersion.Status.PUBLISHED)
            .order_by("-published_at", "-imported_at")
            .first()
        )
    except (RuntimeError, Exception):
        return None


def catalog_version_label() -> str:
    published = get_published_version()
    if published:
        return published.version_label
    return FALLBACK_VERSION


def catalog_meta() -> dict[str, Any]:
    published = get_published_version()
    if published:
        counts = {
            k: published.items.filter(kind=k, is_active=True).count()
            for k, _ in GoodsCatalogItem.Kind.choices
        }
        return {
            "catalog_version": published.version_label,
            "source_hash": published.source_hash,
            "published_at": (
                published.published_at.isoformat() if published.published_at else None
            ),
            **{f"{k}_count": v for k, v in counts.items()},
        }
    return {
        "catalog_version": FALLBACK_VERSION,
        "ncm_count": len(NCM_ITEMS),
        "cfop_count": len(CFOP_ITEMS),
        "unit_count": len(UNIT_ITEMS),
    }


def _codes(kind: str) -> frozenset[str]:
    published = get_published_version()
    if published:
        qs = published.items.filter(kind=kind, is_active=True).values_list("code", flat=True)
        codes = frozenset(qs)
        if codes:
            return codes
    if kind == GoodsCatalogItem.Kind.NCM:
        return _fallback_ncm()
    if kind == GoodsCatalogItem.Kind.CFOP:
        return _fallback_cfop()
    if kind == GoodsCatalogItem.Kind.UNIT:
        return _fallback_units()
    return frozenset()


def catalog_strict() -> bool:
    return bool(getattr(settings, "NFE_CATALOG_STRICT", False))


def validate_ncm(ncm: str) -> str | None:
    code = "".join(ch for ch in str(ncm or "") if ch.isdigit())
    if len(code) != 8:
        return "NCM deve ter 8 dígitos"
    if code not in _codes(GoodsCatalogItem.Kind.NCM):
        return f"NCM {code} fora do catálogo ({catalog_version_label()})"
    return None


def validate_cfop_catalog(cfop: str) -> str | None:
    code = "".join(ch for ch in str(cfop or "") if ch.isdigit())
    if len(code) != 4:
        return "CFOP inválido"
    if code not in _codes(GoodsCatalogItem.Kind.CFOP):
        return f"CFOP {code} fora do catálogo ({catalog_version_label()})"
    return None


def validate_unit(unit: str) -> str | None:
    code = (unit or "").strip().upper()[:6]
    if not code:
        return "Unidade comercial obrigatória"
    if code not in _codes(GoodsCatalogItem.Kind.UNIT):
        return f"Unidade {code} fora do catálogo ({catalog_version_label()})"
    return None


def _cfop_rows(scope: str | None = None) -> list[tuple[str, str]]:
    published = get_published_version()
    if published:
        qs = published.items.filter(kind=GoodsCatalogItem.Kind.CFOP, is_active=True)
        rows: list[tuple[str, str]] = []
        for item in qs.order_by("code"):
            meta = item.metadata if isinstance(item.metadata, dict) else {}
            item_scope = str(meta.get("scope") or "both")
            if scope and item_scope not in {scope, "both"}:
                continue
            rows.append((item.code, item.description or item.code))
        if rows:
            return rows
    out: list[tuple[str, str]] = []
    for code, desc, item_scope in CFOP_ITEMS:
        if scope and item_scope not in {scope, "both"}:
            continue
        out.append((code, desc))
    return out


def _unit_rows() -> list[tuple[str, str]]:
    published = get_published_version()
    if published:
        qs = published.items.filter(kind=GoodsCatalogItem.Kind.UNIT, is_active=True)
        rows = [(i.code, i.description or i.code) for i in qs.order_by("code")]
        if rows:
            return rows
    return list(UNIT_ITEMS)


def dropdown_cfop_internal() -> list[tuple[str, str]]:
    return _cfop_rows("internal")


def dropdown_cfop_interstate() -> list[tuple[str, str]]:
    return _cfop_rows("interstate")


def dropdown_units() -> list[tuple[str, str]]:
    return _unit_rows()


def _source_hash() -> str:
    blob = repr((NCM_ITEMS, CFOP_ITEMS, UNIT_ITEMS)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


@transaction.atomic
def seed_and_publish(*, version_label: str = "goods-v1.0") -> GoodsCatalogVersion:
    """Cria versão publicada a partir do seed estático MVP."""
    GoodsCatalogVersion.objects.filter(status=GoodsCatalogVersion.Status.PUBLISHED).update(
        status=GoodsCatalogVersion.Status.SUPERSEDED
    )
    version, _ = GoodsCatalogVersion.objects.get_or_create(
        version_label=version_label,
        defaults={
            "status": GoodsCatalogVersion.Status.DRAFT,
            "source_hash": _source_hash(),
        },
    )
    version.items.all().delete()
    rows: list[GoodsCatalogItem] = []
    for code, desc in NCM_ITEMS:
        rows.append(
            GoodsCatalogItem(
                version=version,
                kind=GoodsCatalogItem.Kind.NCM,
                code=code,
                description=desc,
            )
        )
    for code, desc, scope in CFOP_ITEMS:
        rows.append(
            GoodsCatalogItem(
                version=version,
                kind=GoodsCatalogItem.Kind.CFOP,
                code=code,
                description=desc,
                metadata={"scope": scope},
            )
        )
    for code, desc in UNIT_ITEMS:
        rows.append(
            GoodsCatalogItem(
                version=version,
                kind=GoodsCatalogItem.Kind.UNIT,
                code=code,
                description=desc,
            )
        )
    GoodsCatalogItem.objects.bulk_create(rows)
    version.row_count = len(rows)
    version.source_hash = _source_hash()
    version.status = GoodsCatalogVersion.Status.PUBLISHED
    version.published_at = timezone.now()
    version.save(
        update_fields=["row_count", "source_hash", "status", "published_at"]
    )
    return version
