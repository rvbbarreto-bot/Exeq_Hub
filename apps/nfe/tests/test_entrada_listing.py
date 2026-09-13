"""Unitários — filtros e KPIs NF-e entrada."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.nfe.entrada.listing import (
    DEFAULT_LIST_DAYS,
    compute_entrada_kpis,
    filter_entrada_queryset,
)
from apps.nfe.entrada.models import NfeEntradaDocument


@pytest.mark.django_db
def test_filter_manifest_and_xml_status(tenant_a, provider_sp):
    pending = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000001",
        manifest_status=NfeEntradaDocument.ManifestStatus.NONE,
        xml_status=NfeEntradaDocument.XmlStatus.PENDING,
    )
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000002",
        schema_type=NfeEntradaDocument.SchemaType.PROC_NFE,
        access_key="35260137229907000137550010000000000000000000002",
        manifest_status=NfeEntradaDocument.ManifestStatus.CIENCIA,
        xml_status=NfeEntradaDocument.XmlStatus.AVAILABLE,
    )
    qs = NfeEntradaDocument.objects.filter(tenant=tenant_a)
    filtered = filter_entrada_queryset(
        qs,
        manifest_status="none",
        xml_status="pending",
        apply_default_period=False,
        days=0,
    )
    assert list(filtered.values_list("id", flat=True)) == [pending.id]


@pytest.mark.django_db
def test_filter_search_by_issuer_and_number(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        issuer_name="FORNECEDOR ALPHA",
        issuer_cnpj="11222333000181",
        number=42,
    )
    qs = NfeEntradaDocument.objects.filter(tenant=tenant_a)
    assert filter_entrada_queryset(qs, q="ALPHA", days=0, apply_default_period=False).get() == doc
    assert filter_entrada_queryset(qs, q="42", days=0, apply_default_period=False).get() == doc
    assert filter_entrada_queryset(
        qs, q="11222333000181", days=0, apply_default_period=False
    ).get() == doc


@pytest.mark.django_db
def test_filter_date_range(tenant_a, provider_sp):
    today = timezone.localdate()
    old = today - timedelta(days=60)
    recent = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        issue_date=today,
    )
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000002",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000002",
        issue_date=old,
    )
    qs = NfeEntradaDocument.objects.filter(tenant=tenant_a)
    filtered = filter_entrada_queryset(
        qs,
        date_from=str(today - timedelta(days=7)),
        date_to=str(today),
        apply_default_period=False,
    )
    assert filtered.count() == 1
    assert filtered.get() == recent


@pytest.mark.django_db
def test_filter_default_period_applies_30_days(tenant_a, provider_sp):
    today = timezone.localdate()
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        issue_date=today - timedelta(days=DEFAULT_LIST_DAYS + 5),
    )
    recent = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000002",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000002",
        issue_date=today,
    )
    qs = NfeEntradaDocument.objects.filter(tenant=tenant_a)
    assert filter_entrada_queryset(qs).get() == recent


@pytest.mark.django_db
def test_filter_days_zero_no_period_limit(tenant_a, provider_sp):
    old_date = date(2020, 1, 1)
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        issue_date=old_date,
    )
    qs = NfeEntradaDocument.objects.filter(tenant=tenant_a)
    assert filter_entrada_queryset(qs, days=0, apply_default_period=False).count() == 1


@pytest.mark.django_db
def test_compute_entrada_kpis(tenant_a, provider_sp):
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        manifest_status=NfeEntradaDocument.ManifestStatus.NONE,
        xml_status=NfeEntradaDocument.XmlStatus.PENDING,
    )
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000002",
        schema_type=NfeEntradaDocument.SchemaType.PROC_NFE,
        access_key="35260137229907000137550010000000000000000000002",
        manifest_status=NfeEntradaDocument.ManifestStatus.CIENCIA,
        xml_status=NfeEntradaDocument.XmlStatus.AVAILABLE,
    )
    kpis = compute_entrada_kpis(NfeEntradaDocument.objects.filter(tenant=tenant_a))
    assert kpis == {
        "total": 2,
        "xml_pending": 1,
        "manifest_pending": 1,
        "xml_available": 1,
    }
