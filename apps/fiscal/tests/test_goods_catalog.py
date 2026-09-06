"""Catálogo mercadorias versionado."""

from __future__ import annotations

import pytest

from apps.fiscal.goods_catalog import (
    catalog_version_label,
    seed_and_publish,
    validate_cfop_catalog,
    validate_ncm,
    validate_unit,
)
from apps.fiscal.models import GoodsCatalogItem, GoodsCatalogVersion


@pytest.mark.django_db
def test_seed_and_publish():
    version = seed_and_publish(version_label="goods-test-1")
    assert version.status == GoodsCatalogVersion.Status.PUBLISHED
    assert version.row_count > 0
    assert GoodsCatalogItem.objects.filter(version=version, kind="ncm").count() >= 10
    assert catalog_version_label() == "goods-test-1"
    assert validate_ncm("21069090") is None
    assert validate_ncm("99999999") is not None
    assert validate_cfop_catalog("5102") is None
    assert validate_unit("UN") is None
    assert validate_unit("ZZZ") is not None


@pytest.mark.django_db
def test_fallback_without_db_seed():
    assert validate_ncm("21069090") is None
    assert validate_ncm("00000000") is not None
