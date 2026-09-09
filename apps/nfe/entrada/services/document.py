"""Upsert idempotente de documentos de entrada."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.accounts.models import Tenant
from apps.master_data.models import Provider
from apps.nfe.entrada.artifacts import is_full_nfe_xml, store_entrada_xml
from apps.nfe.entrada.models import NfeEntradaDocument
from integrations.sefaz_nfe.distribuicao.parse import ParsedDistribuicaoDocument


@dataclass(frozen=True)
class UpsertDocumentResult:
    document: NfeEntradaDocument
    created: bool
    upgraded: bool = False


def _schema_choice(schema_type: str) -> str:
    mapping = {
        "resNFe": NfeEntradaDocument.SchemaType.RES_NFE,
        "procNFe": NfeEntradaDocument.SchemaType.PROC_NFE,
        "resEvento": NfeEntradaDocument.SchemaType.RES_EVENTO,
        "procEventoNFe": NfeEntradaDocument.SchemaType.PROC_EVENTO,
    }
    return mapping.get(schema_type, NfeEntradaDocument.SchemaType.OTHER)


def _apply_parsed_fields(doc: NfeEntradaDocument, parsed: ParsedDistribuicaoDocument) -> None:
    doc.schema_type = _schema_choice(parsed.schema_type)
    if parsed.access_key:
        doc.access_key = parsed.access_key
    if parsed.issuer_cnpj:
        doc.issuer_cnpj = parsed.issuer_cnpj
    if parsed.issuer_name:
        doc.issuer_name = parsed.issuer_name
    if parsed.recipient_cnpj:
        doc.recipient_cnpj = parsed.recipient_cnpj
    if parsed.number is not None:
        doc.number = parsed.number
    if parsed.series is not None:
        doc.series = parsed.series
    if parsed.issue_date is not None:
        doc.issue_date = parsed.issue_date
    if parsed.total_cents is not None:
        doc.total_cents = parsed.total_cents
    if parsed.nfe_status:
        doc.nfe_status = parsed.nfe_status
    doc.raw_metadata = {**(doc.raw_metadata or {}), **parsed.raw_metadata}


def upsert_entrada_document(
    *,
    tenant: Tenant,
    provider: Provider,
    parsed: ParsedDistribuicaoDocument,
) -> UpsertDocumentResult:
    """Idempotente por NSU e por chave de acesso."""
    nsu = parsed.nsu
    existing_nsu = (
        NfeEntradaDocument.objects.filter(tenant=tenant, provider=provider, nsu=nsu).first()
    )
    if existing_nsu is not None:
        return UpsertDocumentResult(document=existing_nsu, created=False)

    if parsed.access_key:
        existing_key = NfeEntradaDocument.objects.filter(
            tenant=tenant,
            access_key=parsed.access_key,
        ).first()
        if existing_key is not None:
            upgraded = False
            if is_full_nfe_xml(parsed.schema_type) and existing_key.xml_status != NfeEntradaDocument.XmlStatus.AVAILABLE:
                _upgrade_to_proc(existing_key, parsed)
                upgraded = True
            return UpsertDocumentResult(document=existing_key, created=False, upgraded=upgraded)

    doc = NfeEntradaDocument(
        tenant=tenant,
        provider=provider,
        nsu=nsu,
        schema_type=_schema_choice(parsed.schema_type),
        access_key=parsed.access_key or "",
        issuer_cnpj=parsed.issuer_cnpj,
        issuer_name=parsed.issuer_name,
        recipient_cnpj=parsed.recipient_cnpj or "".join(c for c in provider.document if c.isdigit())[:14],
        number=parsed.number,
        series=parsed.series,
        issue_date=parsed.issue_date,
        total_cents=parsed.total_cents,
        nfe_status=parsed.nfe_status,
        xml_hash=parsed.xml_hash,
        raw_metadata=parsed.raw_metadata,
    )
    if is_full_nfe_xml(parsed.schema_type):
        doc.xml_status = NfeEntradaDocument.XmlStatus.AVAILABLE
        doc.stored_file = store_entrada_xml(
            tenant_id=tenant.id,
            provider=provider,
            access_key=parsed.access_key,
            xml_bytes=parsed.xml_bytes,
        )
    else:
        doc.xml_status = NfeEntradaDocument.XmlStatus.PENDING

    try:
        with transaction.atomic():
            doc.save()
    except IntegrityError:
        dup = NfeEntradaDocument.objects.filter(tenant=tenant, provider=provider, nsu=nsu).first()
        if dup is not None:
            return UpsertDocumentResult(document=dup, created=False)
        if parsed.access_key:
            dup = NfeEntradaDocument.objects.filter(tenant=tenant, access_key=parsed.access_key).first()
            if dup is not None:
                return UpsertDocumentResult(document=dup, created=False)
        raise

    return UpsertDocumentResult(document=doc, created=True)


def _upgrade_to_proc(doc: NfeEntradaDocument, parsed: ParsedDistribuicaoDocument) -> None:
    _apply_parsed_fields(doc, parsed)
    doc.xml_status = NfeEntradaDocument.XmlStatus.AVAILABLE
    doc.xml_hash = parsed.xml_hash
    if doc.stored_file_id is None and parsed.access_key:
        doc.stored_file = store_entrada_xml(
            tenant_id=doc.tenant_id,
            provider=doc.provider,
            access_key=parsed.access_key,
            xml_bytes=parsed.xml_bytes,
        )
    doc.save()
