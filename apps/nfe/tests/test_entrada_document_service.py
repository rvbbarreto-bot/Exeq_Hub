"""Unitários — upsert documento NF-e entrada."""

from __future__ import annotations

from datetime import date

import pytest

from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.services.document import upsert_entrada_document
from integrations.sefaz_nfe.distribuicao.parse import ParsedDistribuicaoDocument
from integrations.sefaz_nfe.distribuicao.stub_xml import build_stub_res_nfe_xml

KEY = "35260137229907000137550010000000000000000000001"
KEY2 = "35260137229907000137550010000000000000000000002"


def _parsed(*, nsu: str, key: str = KEY, schema: str = "resNFe", xml: bytes | None = None):
    xml_bytes = xml or build_stub_res_nfe_xml(access_key=key)
    return ParsedDistribuicaoDocument(
        nsu=nsu,
        schema_type=schema,
        access_key=key,
        issuer_cnpj="11222333000181",
        issuer_name="FORN STUB",
        recipient_cnpj="37229907000137",
        number=1,
        series=1,
        issue_date=date(2026, 1, 15),
        total_cents=100000,
        nfe_status="1",
        xml_bytes=xml_bytes,
        xml_hash="abc123",
        raw_metadata={"source": "test"},
    )


@pytest.mark.django_db
def test_upsert_creates_res_nfe_pending_xml(tenant_a, provider_sp):
    result = upsert_entrada_document(
        tenant=tenant_a,
        provider=provider_sp,
        parsed=_parsed(nsu="000000000000001"),
    )
    assert result.created is True
    doc = result.document
    assert doc.xml_status == NfeEntradaDocument.XmlStatus.PENDING
    assert doc.stored_file_id is None
    assert doc.issuer_name == "FORN STUB"


@pytest.mark.django_db
def test_upsert_idempotent_by_nsu(tenant_a, provider_sp):
    first = upsert_entrada_document(
        tenant=tenant_a, provider=provider_sp, parsed=_parsed(nsu="000000000000001")
    )
    second = upsert_entrada_document(
        tenant=tenant_a, provider=provider_sp, parsed=_parsed(nsu="000000000000001")
    )
    assert first.created is True
    assert second.created is False
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 1


@pytest.mark.django_db
def test_upsert_proc_nfe_stores_xml(tenant_a, provider_sp):
    result = upsert_entrada_document(
        tenant=tenant_a,
        provider=provider_sp,
        parsed=_parsed(nsu="000000000000001", schema="procNFe"),
    )
    doc = result.document
    assert doc.xml_status == NfeEntradaDocument.XmlStatus.AVAILABLE
    assert doc.stored_file_id is not None


@pytest.mark.django_db
def test_upsert_upgrades_res_to_proc_by_access_key(tenant_a, provider_sp):
    upsert_entrada_document(
        tenant=tenant_a,
        provider=provider_sp,
        parsed=_parsed(nsu="000000000000001", key=KEY, schema="resNFe"),
    )
    result = upsert_entrada_document(
        tenant=tenant_a,
        provider=provider_sp,
        parsed=_parsed(nsu="000000000000099", key=KEY, schema="procNFe"),
    )
    assert result.created is False
    assert result.upgraded is True
    doc = result.document
    assert doc.xml_status == NfeEntradaDocument.XmlStatus.AVAILABLE
    assert doc.stored_file_id is not None
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a, access_key=KEY).count() == 1


@pytest.mark.django_db
def test_upsert_different_keys_same_tenant(tenant_a, provider_sp):
    upsert_entrada_document(
        tenant=tenant_a, provider=provider_sp, parsed=_parsed(nsu="000000000000001", key=KEY)
    )
    upsert_entrada_document(
        tenant=tenant_a, provider=provider_sp, parsed=_parsed(nsu="000000000000002", key=KEY2)
    )
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 2
