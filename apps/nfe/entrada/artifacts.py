"""Persistência de XML NF-e de entrada."""

from __future__ import annotations

from uuid import uuid4

from apps.nfe.entrada.models import NfeEntradaDocument
from apps.master_data.models import Provider
from apps.ops.models import StoredFile
from shared.storage import StorageError, get_storage


def store_entrada_xml(
    *,
    tenant_id,
    provider: Provider,
    access_key: str,
    xml_bytes: bytes,
) -> StoredFile:
    if not xml_bytes:
        raise StorageError("XML vazio")
    key_part = access_key or uuid4().hex
    object_key = f"nfe_entrada/{tenant_id}/{provider.id}/{key_part}.xml"
    storage = get_storage()
    storage.put(key=object_key, data=xml_bytes, content_type="application/xml")
    return StoredFile.objects.create(
        tenant_id=tenant_id,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type="application/xml",
        size_bytes=len(xml_bytes),
        checksum_sha256=StoredFile.checksum(xml_bytes),
        encryption="none",
        purpose="nfe_entrada_xml",
    )


def store_manifest_xml(
    *,
    tenant_id,
    document_id,
    tp_evento: str,
    xml_bytes: bytes,
) -> StoredFile:
    if not xml_bytes:
        raise StorageError("XML evento vazio")
    object_key = f"nfe_entrada/{tenant_id}/manifest/{document_id}/{tp_evento}-{uuid4().hex[:10]}.xml"
    storage = get_storage()
    storage.put(key=object_key, data=xml_bytes, content_type="application/xml")
    return StoredFile.objects.create(
        tenant_id=tenant_id,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type="application/xml",
        size_bytes=len(xml_bytes),
        checksum_sha256=StoredFile.checksum(xml_bytes),
        encryption="none",
        purpose="nfe_entrada_manifest_xml",
    )


def is_full_nfe_xml(schema_type: str) -> bool:
    return schema_type == NfeEntradaDocument.SchemaType.PROC_NFE


def read_entrada_xml_bytes(document: NfeEntradaDocument) -> bytes:
    if not document.stored_file_id:
        raise StorageError("XML ainda não disponível")
    stored = document.stored_file
    if stored is None:
        raise StorageError("Arquivo XML não encontrado")
    return get_storage().get(key=stored.object_key)
