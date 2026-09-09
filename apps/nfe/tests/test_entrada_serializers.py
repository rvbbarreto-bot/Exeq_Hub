"""Unitários — serializers NF-e entrada."""

from __future__ import annotations

from datetime import date

import pytest
from django.utils import timezone

from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.models import NfeEntradaDocument, NfeEntradaManifestation
from apps.nfe.entrada.serializers import (
    NfeDistribuicaoConfigSerializer,
    NfeDistribuicaoStatusSerializer,
    NfeEntradaDocumentDetailSerializer,
    NfeEntradaDocumentSerializer,
    NfeEntradaManifestRequestSerializer,
    NfeEntradaSyncSerializer,
)
from integrations.sefaz_nfe.manifestacao.evento import TP_EVENTO_CIENCIA, TP_EVENTO_CONFIRMACAO


@pytest.mark.django_db
def test_document_serializer_has_xml_flag(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        issuer_name="FORN",
        issue_date=date(2026, 1, 15),
        total_cents=100000,
    )
    data = NfeEntradaDocumentSerializer(doc).data
    assert data["provider_name"] == provider_sp.legal_name
    assert data["has_xml"] is False
    assert data["manifest_status"] == "none"


@pytest.mark.django_db
def test_detail_serializer_includes_manifestations(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
    )
    NfeEntradaManifestation.objects.create(
        tenant=tenant_a,
        document=doc,
        tp_evento=NfeEntradaManifestation.EventType.CIENCIA,
        status=NfeEntradaManifestation.Status.ACCEPTED,
        protocol="135000000000001",
    )
    data = NfeEntradaDocumentDetailSerializer(doc).data
    assert len(data["manifestations"]) == 1
    assert data["manifestations"][0]["tp_evento"] == TP_EVENTO_CIENCIA


@pytest.mark.django_db
def test_distribuicao_status_blocked_flag(tenant_a, provider_sp):
    cursor = get_or_create_cursor(tenant=tenant_a, provider=provider_sp)
    cursor.blocked_until = timezone.now() + timezone.timedelta(hours=1)
    cursor.save()
    data = NfeDistribuicaoStatusSerializer(cursor).data
    assert data["blocked"] is True
    assert data["cnpj"] == "37229907000137"


def test_sync_serializer_optional_provider():
    ser = NfeEntradaSyncSerializer(data={})
    assert ser.is_valid()


def test_manifest_request_requires_tp_evento():
    ser = NfeEntradaManifestRequestSerializer(data={"confirmed": True})
    assert not ser.is_valid()
    ser = NfeEntradaManifestRequestSerializer(
        data={"tp_evento": TP_EVENTO_CONFIRMACAO, "confirmed": True}
    )
    assert ser.is_valid()


def test_config_serializer_interval_bounds():
    ser = NfeDistribuicaoConfigSerializer(
        data={
            "provider_id": "00000000-0000-0000-0000-000000000001",
            "interval_seconds": 100,
        }
    )
    assert not ser.is_valid()
