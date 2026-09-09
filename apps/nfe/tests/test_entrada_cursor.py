"""Unitários — cursor NSU."""

from __future__ import annotations

import pytest

from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.models import NfeDistribuicaoCursor


@pytest.mark.django_db
def test_get_or_create_cursor_defaults(tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    assert cursor.cnpj == "37229907000137"
    assert cursor.ult_nsu == "0"
    assert cursor.tp_amb in ("1", "2")


@pytest.mark.django_db
def test_get_or_create_cursor_idempotent(tenant_a, provider_sp):
    first = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    second = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    assert first.id == second.id
    assert NfeDistribuicaoCursor.objects.filter(tenant=tenant_a).count() == 1


@pytest.mark.django_db
def test_get_or_create_updates_cnpj_if_provider_document_changes(tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    provider_sp.document = "11222333000181"
    provider_sp.save(update_fields=["document"])
    updated = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    assert updated.id == cursor.id
    assert updated.cnpj == "11222333000181"
