"""Helpers NF-e no Hub V4 (download artefatos; sem alterar domínio fiscal)."""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from apps.nfe.artifacts import get_artifact, has_danfe_pdf, has_xml_authorized, has_xml_cce, read_artifact_bytes
from apps.nfe.models import NfeArtifact, NfeInvoice

# URL segment → (kind model, content_type, filename prefix)
NFE_DOWNLOAD_KINDS = {
    "xml": (NfeArtifact.Kind.XML_AUTHORIZED, "application/xml; charset=utf-8", "nfe"),
    "pdf": (NfeArtifact.Kind.DANFE_PDF, "application/pdf", "danfe"),
    "cce": (NfeArtifact.Kind.XML_CCE, "application/xml; charset=utf-8", "cce"),
    "xml-cancel": (
        NfeArtifact.Kind.XML_CANCEL,
        "application/xml; charset=utf-8",
        "nfe-cancel",
    ),
}


def nfe_artifact_flags(invoice: NfeInvoice) -> dict[str, bool]:
    return {
        "xml": has_xml_authorized(invoice),
        "pdf": has_danfe_pdf(invoice),
        "cce": has_xml_cce(invoice),
        "xml_cancel": bool(
            get_artifact(invoice, NfeArtifact.Kind.XML_CANCEL) is not None
        ),
    }


def download_nfe_artifact(*, tenant, invoice_id, kind: str) -> HttpResponse:
    key = (kind or "").strip().lower()
    if key not in NFE_DOWNLOAD_KINDS:
        raise Http404("Tipo de documento inválido")
    inv = get_object_or_404(NfeInvoice, pk=invoice_id, tenant=tenant)
    if inv.status not in {
        NfeInvoice.Status.AUTHORIZED,
        NfeInvoice.Status.CANCELLED,
    }:
        raise Http404("Artefatos disponíveis só para NF-e autorizada ou cancelada")
    model_kind, content_type, prefix = NFE_DOWNLOAD_KINDS[key]
    art = get_artifact(inv, model_kind)
    if art is None:
        raise Http404("Documento ainda não disponível")
    data = read_artifact_bytes(art)
    ext = "pdf" if key == "pdf" else "xml"
    ref = (inv.access_key or str(inv.id))[:44]
    filename = f"{prefix}-{ref}.{ext}"
    resp = HttpResponse(data, content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    if art.checksum_sha256:
        resp["X-Checksum-SHA256"] = art.checksum_sha256
    return resp
