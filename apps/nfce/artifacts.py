"""Persistência de artefatos NFC-e (XML + DANFE cupom)."""

from __future__ import annotations

import logging
from uuid import uuid4

from apps.nfce.models import NfceArtifact, NfceInvoice
from apps.nfce.xml_export import resolve_authorized_xml_bytes
from apps.ops.models import StoredFile
from shared.storage import get_storage

logger = logging.getLogger(__name__)

DANFCE_LAYOUT_VERSION = "exeq-danfce-0.1"


def has_artifact(invoice: NfceInvoice, kind: str) -> bool:
    return NfceArtifact.objects.filter(invoice_id=invoice.id, kind=kind).exists()


def get_artifact(invoice: NfceInvoice, kind: str) -> NfceArtifact | None:
    return (
        NfceArtifact.objects.select_related("stored_file")
        .filter(invoice_id=invoice.id, kind=kind)
        .first()
    )


def read_artifact_bytes(artifact: NfceArtifact) -> bytes:
    storage = get_storage()
    return storage.get(key=artifact.stored_file.object_key)


def store_artifact(
    invoice: NfceInvoice,
    *,
    kind: str,
    data: bytes,
    content_type: str,
    filename_prefix: str,
    extension: str,
    purpose: str,
) -> NfceArtifact:
    existing = get_artifact(invoice, kind)
    if existing is not None:
        return existing
    if not data:
        raise ValueError("artefato vazio")

    object_key = (
        f"nfce/{invoice.tenant_id}/{invoice.id}/"
        f"{filename_prefix}-{uuid4().hex[:10]}.{extension}"
    )
    storage = get_storage()
    storage.put(key=object_key, data=data, content_type=content_type)
    stored = StoredFile.objects.create(
        tenant_id=invoice.tenant_id,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type=content_type,
        size_bytes=len(data),
        checksum_sha256=StoredFile.checksum(data),
        encryption="none",
        purpose=purpose,
    )
    return NfceArtifact.objects.create(
        tenant_id=invoice.tenant_id,
        invoice=invoice,
        kind=kind,
        stored_file=stored,
        checksum_sha256=stored.checksum_sha256,
    )


def ensure_authorized_artifacts(
    invoice: NfceInvoice,
    *,
    xml_bytes: bytes | None = None,
) -> None:
    invoice.refresh_from_db()
    if invoice.status != NfceInvoice.Status.AUTHORIZED:
        return

    data = xml_bytes
    if not data:
        data = resolve_authorized_xml_bytes(invoice)
    if not data:
        logger.warning("nfce_artifact_xml_missing invoice=%s", invoice.id)
        return

    try:
        store_artifact(
            invoice,
            kind=NfceArtifact.Kind.XML_AUTHORIZED,
            data=data,
            content_type="application/xml",
            filename_prefix="nfce",
            extension="xml",
            purpose="nfce_xml_authorized",
        )
    except Exception:  # noqa: BLE001
        logger.exception("nfce_artifact_xml_store_failed invoice=%s", invoice.id)

    try:
        from integrations.sefaz_nfe.danfe_nfce import render_danfce_pdf

        pdf = render_danfce_pdf(data)
        if pdf and pdf.startswith(b"%PDF"):
            store_artifact(
                invoice,
                kind=NfceArtifact.Kind.DANFE_PDF,
                data=pdf,
                content_type="application/pdf",
                filename_prefix="danfce",
                extension="pdf",
                purpose="nfce_danfce_pdf",
            )
    except Exception:  # noqa: BLE001
        logger.exception("nfce_danfce_render_failed invoice=%s", invoice.id)


def ensure_cancelled_artifacts(invoice: NfceInvoice) -> None:
    invoice.refresh_from_db()
    if invoice.status != NfceInvoice.Status.CANCELLED:
        return
    data = resolve_authorized_xml_bytes(invoice)
    if not data:
        return
    try:
        from integrations.sefaz_nfe.danfe_nfce import render_danfce_pdf

        pdf = render_danfce_pdf(data, cancelled=True)
        if pdf and pdf.startswith(b"%PDF"):
            NfceArtifact.objects.filter(
                invoice_id=invoice.id, kind=NfceArtifact.Kind.DANFE_PDF
            ).delete()
            store_artifact(
                invoice,
                kind=NfceArtifact.Kind.DANFE_PDF,
                data=pdf,
                content_type="application/pdf",
                filename_prefix="danfce-cancelada",
                extension="pdf",
                purpose="nfce_danfce_pdf_cancelled",
            )
    except Exception:  # noqa: BLE001
        logger.exception("nfce_danfce_cancel_render_failed invoice=%s", invoice.id)
