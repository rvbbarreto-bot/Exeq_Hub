"""Persistência de artefatos NF-e (XML + DANFE) — U3/I1–I2."""

from __future__ import annotations

import logging
from uuid import uuid4

from apps.nfe.models import NfeArtifact, NfeInvoice
from apps.ops.models import StoredFile
from shared.storage import get_storage

logger = logging.getLogger(__name__)

DANFE_LAYOUT_VERSION = "exeq-danfe-0.1"


def has_artifact(invoice: NfeInvoice, kind: str) -> bool:
    return NfeArtifact.objects.filter(invoice_id=invoice.id, kind=kind).exists()


def has_xml_authorized(invoice: NfeInvoice) -> bool:
    return has_artifact(invoice, NfeArtifact.Kind.XML_AUTHORIZED)


def has_danfe_pdf(invoice: NfeInvoice) -> bool:
    return has_artifact(invoice, NfeArtifact.Kind.DANFE_PDF)


def get_artifact(invoice: NfeInvoice, kind: str) -> NfeArtifact | None:
    return (
        NfeArtifact.objects.select_related("stored_file")
        .filter(invoice_id=invoice.id, kind=kind)
        .first()
    )


def store_artifact(
    invoice: NfeInvoice,
    *,
    kind: str,
    data: bytes,
    content_type: str,
    filename_prefix: str,
    extension: str,
    purpose: str,
) -> NfeArtifact:
    """Idempotente: retorna existente se kind já gravado (não sobrescreve)."""
    existing = get_artifact(invoice, kind)
    if existing is not None:
        return existing
    if not data:
        raise ValueError("artefato vazio")

    object_key = (
        f"nfe/{invoice.tenant_id}/{invoice.id}/"
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
    return NfeArtifact.objects.create(
        tenant_id=invoice.tenant_id,
        invoice=invoice,
        kind=kind,
        stored_file=stored,
        checksum_sha256=stored.checksum_sha256,
    )


def resolve_authorized_xml_bytes(
    invoice: NfeInvoice,
    *,
    xml_bytes: bytes | None = None,
    provider_raw: dict | None = None,
) -> bytes | None:
    """Preferência: bytes explícitos → raw do adapter → snapshot → XML sintético."""
    if xml_bytes:
        return xml_bytes

    raw = provider_raw or {}
    inline = raw.get("xml") or raw.get("nfe_xml") or raw.get("xml_nfe")
    if isinstance(inline, str) and "<" in inline:
        return inline.encode("utf-8")
    if isinstance(inline, (bytes, bytearray)):
        return bytes(inline)

    snap = invoice.fiscal_snapshot
    if isinstance(snap, dict) and snap:
        try:
            from integrations.sefaz_nfe.xml_nfe import build_nfe_xml

            return build_nfe_xml(snapshot=snap, access_key=invoice.access_key or None)
        except Exception:  # noqa: BLE001
            logger.exception("nfe_artifact_xml_from_snapshot_failed invoice=%s", invoice.id)
    return None


def _set_pdf_pending(invoice: NfeInvoice, *, pending: bool) -> None:
    """D-10 / EX-PDF: flag ops sem desfazer authorized."""
    flags = dict(invoice.last_validation or {})
    if pending:
        flags["pdf_pending"] = True
        flags["danfe_layout_version"] = DANFE_LAYOUT_VERSION
    else:
        flags.pop("pdf_pending", None)
        flags["danfe_layout_version"] = DANFE_LAYOUT_VERSION
    if invoice.last_validation != flags:
        invoice.last_validation = flags
        invoice.save(update_fields=["last_validation", "updated_at"])


def ensure_authorized_xml(
    invoice: NfeInvoice,
    *,
    xml_bytes: bytes | None = None,
    provider_raw: dict | None = None,
) -> NfeArtifact | None:
    invoice.refresh_from_db()
    if invoice.status != NfeInvoice.Status.AUTHORIZED:
        return None

    existing = get_artifact(invoice, NfeArtifact.Kind.XML_AUTHORIZED)
    if existing is not None:
        return existing

    data = resolve_authorized_xml_bytes(
        invoice, xml_bytes=xml_bytes, provider_raw=provider_raw
    )
    if not data:
        logger.warning("nfe_artifact_xml_missing invoice=%s", invoice.id)
        return None
    try:
        return store_artifact(
            invoice,
            kind=NfeArtifact.Kind.XML_AUTHORIZED,
            data=data,
            content_type="application/xml",
            filename_prefix="nfe",
            extension="xml",
            purpose="nfe_xml_authorized",
        )
    except Exception:  # noqa: BLE001
        logger.exception("nfe_artifact_xml_store_failed invoice=%s", invoice.id)
        return None


def ensure_danfe_pdf(
    invoice: NfeInvoice,
    *,
    xml_bytes: bytes | None = None,
    cancelled: bool = False,
) -> NfeArtifact | None:
    """
    Garante DANFE PDF. Falha de renderização NÃO reverte status da nota (D-10).
    Idempotente para o kind danfe_pdf (substitui se cancelled regenerar).
    """
    invoice.refresh_from_db()
    if invoice.status not in {
        NfeInvoice.Status.AUTHORIZED,
        NfeInvoice.Status.CANCELLED,
    }:
        return None

    if not cancelled and invoice.status == NfeInvoice.Status.AUTHORIZED:
        existing = get_artifact(invoice, NfeArtifact.Kind.DANFE_PDF)
        if existing is not None:
            _set_pdf_pending(invoice, pending=False)
            return existing

    data_xml = xml_bytes
    if data_xml is None:
        xml_art = get_artifact(invoice, NfeArtifact.Kind.XML_AUTHORIZED)
        if xml_art is not None:
            data_xml = read_artifact_bytes(xml_art)
        else:
            data_xml = resolve_authorized_xml_bytes(invoice)
    if not data_xml:
        logger.warning("nfe_danfe_no_xml invoice=%s", invoice.id)
        _set_pdf_pending(invoice, pending=True)
        return None

    try:
        from integrations.sefaz_nfe.danfe import render_danfe_pdf

        pdf = render_danfe_pdf(
            data_xml,
            cancelled=cancelled or invoice.status == NfeInvoice.Status.CANCELLED,
        )
    except Exception:  # noqa: BLE001 — D-10
        logger.exception("nfe_danfe_render_failed invoice=%s", invoice.id)
        _set_pdf_pending(invoice, pending=True)
        return None

    if not pdf or not pdf.startswith(b"%PDF"):
        _set_pdf_pending(invoice, pending=True)
        return None

    if cancelled or invoice.status == NfeInvoice.Status.CANCELLED:
        old = get_artifact(invoice, NfeArtifact.Kind.DANFE_PDF)
        if old is not None:
            old.delete()

    try:
        art = store_artifact(
            invoice,
            kind=NfeArtifact.Kind.DANFE_PDF,
            data=pdf,
            content_type="application/pdf",
            filename_prefix="danfe" if not cancelled else "danfe-cancelada",
            extension="pdf",
            purpose="nfe_danfe_pdf",
        )
        _set_pdf_pending(invoice, pending=False)
        return art
    except Exception:  # noqa: BLE001
        logger.exception("nfe_danfe_store_failed invoice=%s", invoice.id)
        _set_pdf_pending(invoice, pending=True)
        return None


def ensure_authorized_artifacts(
    invoice: NfeInvoice,
    *,
    xml_bytes: bytes | None = None,
    provider_raw: dict | None = None,
) -> list[NfeArtifact]:
    """XML + DANFE após authorize. PDF pending não desfaz authorized."""
    created: list[NfeArtifact] = []
    xml_art = ensure_authorized_xml(
        invoice, xml_bytes=xml_bytes, provider_raw=provider_raw
    )
    if xml_art:
        created.append(xml_art)
        xml_data = read_artifact_bytes(xml_art)
    else:
        xml_data = resolve_authorized_xml_bytes(
            invoice, xml_bytes=xml_bytes, provider_raw=provider_raw
        )
    pdf_art = ensure_danfe_pdf(invoice, xml_bytes=xml_data, cancelled=False)
    if pdf_art:
        created.append(pdf_art)
    elif has_xml_authorized(invoice) and not has_danfe_pdf(invoice):
        _set_pdf_pending(invoice, pending=True)
        logger.warning("EX-PDF-01: DANFE pendente invoice=%s (authorized mantido)", invoice.id)
    return created


def ensure_cancel_xml(
    invoice: NfeInvoice,
    *,
    xml_bytes: bytes | None = None,
    provider_raw: dict | None = None,
) -> NfeArtifact | None:
    """Persiste XML do evento de cancelamento (I6). Idempotente por kind."""
    invoice.refresh_from_db()
    if invoice.status != NfeInvoice.Status.CANCELLED:
        return None
    existing = get_artifact(invoice, NfeArtifact.Kind.XML_CANCEL)
    if existing is not None:
        return existing

    data = xml_bytes
    if not data and provider_raw:
        inline = provider_raw.get("xml") or provider_raw.get("evento_xml")
        if isinstance(inline, str) and "<" in inline:
            data = inline.encode("utf-8")
        elif isinstance(inline, (bytes, bytearray)):
            data = bytes(inline)
    if not data:
        logger.warning("nfe_artifact_xml_cancel_missing invoice=%s", invoice.id)
        return None
    try:
        return store_artifact(
            invoice,
            kind=NfeArtifact.Kind.XML_CANCEL,
            data=data,
            content_type="application/xml",
            filename_prefix="nfe-canc",
            extension="xml",
            purpose="nfe_xml_cancel",
        )
    except Exception:  # noqa: BLE001
        logger.exception("nfe_artifact_xml_cancel_store_failed invoice=%s", invoice.id)
        return None


def read_artifact_bytes(artifact: NfeArtifact) -> bytes:
    storage = get_storage()
    return storage.get(key=artifact.stored_file.object_key)
