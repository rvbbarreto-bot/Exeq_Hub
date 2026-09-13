"""Unitários — artifacts NF-e entrada (storage)."""

from __future__ import annotations

import pytest

from apps.nfe.entrada.artifacts import (
    is_full_nfe_xml,
    read_entrada_xml_bytes,
    store_entrada_xml,
    store_manifest_xml,
)
from apps.nfe.entrada.models import NfeEntradaDocument
from apps.ops.models import StoredFile
from shared.storage import StorageError, get_storage


@pytest.mark.django_db
def test_store_and_read_entrada_xml(tenant_a, provider_sp):
    xml = b"<nfeProc>stub</nfeProc>"
    stored = store_entrada_xml(
        tenant_id=tenant_a.id,
        provider=provider_sp,
        access_key="35260137229907000137550010000000000000000000001",
        xml_bytes=xml,
    )
    assert stored.purpose == "nfe_entrada_xml"
    assert get_storage().get(key=stored.object_key) == xml

    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.PROC_NFE,
        access_key="35260137229907000137550010000000000000000000001",
        xml_status=NfeEntradaDocument.XmlStatus.AVAILABLE,
        stored_file=stored,
    )
    assert read_entrada_xml_bytes(doc) == xml


@pytest.mark.django_db
def test_store_manifest_xml(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
    )
    xml = b"<envEvento>stub</envEvento>"
    stored = store_manifest_xml(
        tenant_id=tenant_a.id,
        document_id=doc.id,
        tp_evento="210210",
        xml_bytes=xml,
    )
    assert stored.purpose == "nfe_entrada_manifest_xml"
    assert StoredFile.objects.filter(tenant=tenant_a, pk=stored.id).exists()


def test_store_empty_xml_raises():
    with pytest.raises(StorageError, match="XML vazio"):
        store_entrada_xml(
            tenant_id="00000000-0000-0000-0000-000000000001",
            provider=type("P", (), {"id": "x"})(),
            access_key="k",
            xml_bytes=b"",
        )


@pytest.mark.django_db
def test_read_entrada_xml_missing_file(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key="35260137229907000137550010000000000000000000001",
    )
    with pytest.raises(StorageError, match="indisponível"):
        read_entrada_xml_bytes(doc)


def test_is_full_nfe_xml():
    assert is_full_nfe_xml("procNFe") is True
    assert is_full_nfe_xml("resNFe") is False
