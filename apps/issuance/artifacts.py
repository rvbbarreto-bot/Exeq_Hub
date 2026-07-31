"""Persistência de artefatos NFS-e (DANFSe PDF / XML) em StoredFile."""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx
from django.conf import settings

from apps.issuance.models import NfArtifact, NfIssue
from apps.ops.models import StoredFile
from shared.storage import get_storage

logger = logging.getLogger(__name__)

# PDF mínimo quando Focus stub não devolve URL (dev/QA offline legado).
_STUB_DANFSE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
)

_STUB_NFSE_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<NfseStub EXEQ=\"1\"><InfNfse><Numero>0</Numero></InfNfse></NfseStub>"
)


def _set_pdf_pending(issue: NfIssue, *, pending: bool) -> None:
    """EX-PDF-01 — flag ops sem desfazer authorized."""
    raw = dict(issue.focus_status_raw or {})
    if pending:
        raw["pdf_pending"] = True
    else:
        raw.pop("pdf_pending", None)
    if issue.focus_status_raw != raw:
        issue.focus_status_raw = raw
        issue.save(update_fields=["focus_status_raw", "updated_at"])


def ensure_authorized_artifacts(issue: NfIssue) -> list[NfArtifact]:
    """Garante NfArtifact PDF + XML após autorização. Idempotente por kind."""
    issue.refresh_from_db()
    if issue.status != NfIssue.Status.AUTHORIZED:
        return []

    created: list[NfArtifact] = []
    xml_bytes = _resolve_xml_bytes(issue)
    pdf = _ensure_kind(
        issue,
        kind=NfArtifact.Kind.PDF,
        purpose="nf_pdf",
        filename_prefix="danfse",
        extension="pdf",
        content_type="application/pdf",
        data=_resolve_danfse_bytes(issue, xml_bytes=xml_bytes, cancelled=False),
    )
    if pdf:
        created.append(pdf)

    xml = _ensure_kind(
        issue,
        kind=NfArtifact.Kind.XML,
        purpose="nf_xml",
        filename_prefix="nfse",
        extension="xml",
        content_type="application/xml",
        data=xml_bytes,
    )
    if xml:
        created.append(xml)

    # EX-PDF-01: XML ok + PDF falhou → authorized permanece; flag pdf_pending.
    has_pdf = NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.PDF).exists()
    has_xml = NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.XML).exists()
    if has_xml and not has_pdf:
        _set_pdf_pending(issue, pending=True)
        logger.warning("EX-PDF-01: PDF pendente issue=%s (authorized mantido)", issue.id)
    elif has_pdf:
        _set_pdf_pending(issue, pending=False)

    return created


def ensure_cancelled_artifacts(issue: NfIssue) -> list[NfArtifact]:
    """Regenera DANFSe com marca CANCELADA (RF-32/43). Substitui PDF existente."""
    issue.refresh_from_db()
    if issue.status != NfIssue.Status.CANCELLED:
        return []

    xml_bytes = _resolve_xml_bytes(issue)
    if not xml_bytes:
        logger.warning("EX-PDF-03: XML ausente ao regenerar DANFSe cancelada issue=%s", issue.id)
        return []

    pdf_bytes = _generate_hub_danfse(xml_bytes, cancelled=True)
    if not pdf_bytes:
        logger.warning("EX-PDF-03: falha ao regenerar DANFSe cancelada issue=%s", issue.id)
        return []

    existing = NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.PDF).first()
    if existing:
        existing.delete()

    art = _ensure_kind(
        issue,
        kind=NfArtifact.Kind.PDF,
        purpose="nf_pdf",
        filename_prefix="danfse-cancelada",
        extension="pdf",
        content_type="application/pdf",
        data=pdf_bytes,
    )
    return [art] if art else []


def regenerate_danfse_pdf(issue: NfIssue) -> NfArtifact | None:
    """Substitui PDF pelo layout atual (autorizada ou cancelada). XML permanece."""
    issue.refresh_from_db()
    if issue.status == NfIssue.Status.CANCELLED:
        arts = ensure_cancelled_artifacts(issue)
        return arts[0] if arts else None
    if issue.status != NfIssue.Status.AUTHORIZED:
        return None
    NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.PDF).delete()
    arts = ensure_authorized_artifacts(issue)
    return next((a for a in arts if a.kind == NfArtifact.Kind.PDF), None)


def _ensure_kind(
    issue: NfIssue,
    *,
    kind: str,
    purpose: str,
    filename_prefix: str,
    extension: str,
    content_type: str,
    data: bytes | None,
) -> NfArtifact | None:
    existing = NfArtifact.objects.filter(nf_issue=issue, kind=kind).first()
    if existing:
        return existing
    if not data:
        return None

    object_key = (
        f"nf/{issue.tenant_id}/{issue.id}/"
        f"{filename_prefix}-{uuid4().hex[:10]}.{extension}"
    )
    storage = get_storage()
    storage.put(key=object_key, data=data, content_type=content_type)
    stored = StoredFile.objects.create(
        tenant=issue.tenant,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type=content_type,
        size_bytes=len(data),
        checksum_sha256=StoredFile.checksum(data),
        encryption="none",
        purpose=purpose,
    )
    return NfArtifact.objects.create(
        tenant=issue.tenant,
        nf_issue=issue,
        kind=kind,
        stored_file=stored,
        checksum_sha256=stored.checksum_sha256,
    )


def _resolve_danfse_bytes(
    issue: NfIssue,
    *,
    xml_bytes: bytes | None,
    cancelled: bool,
) -> bytes | None:
    if xml_bytes:
        pdf = _generate_hub_danfse(xml_bytes, cancelled=cancelled)
        if pdf:
            return pdf
        logger.warning(
            "EX-PDF-01: falha ao gerar DANFSe Hub issue=%s — tentando fallback",
            issue.id,
        )

    raw = issue.focus_status_raw or {}
    data = _fetch_focus_bytes(
        raw.get("url_danfse")
        or raw.get("caminho_danfse")
        or raw.get("url_pdf")
        or ""
    )
    if data and (data.startswith(b"%PDF") or len(data) > 100):
        return data
    if _is_focus_stub_mode() and (raw.get("provider") or "focus") != "sefin":
        return _STUB_DANFSE_PDF
    return None


def _generate_hub_danfse(xml_bytes: bytes, *, cancelled: bool) -> bytes | None:
    try:
        import time

        from integrations.nfse.danfse import render_danfse_pdf

        t0 = time.perf_counter()
        pdf = render_danfse_pdf(xml_bytes, cancelled=cancelled)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "nfse.pdf_ms=%.0f cancelled=%s bytes=%s",
            elapsed_ms,
            cancelled,
            len(pdf) if pdf else 0,
        )
        return pdf
    except Exception:  # noqa: BLE001 — EX-PDF-01: não desfaz autorização
        logger.exception("Falha na geração DANFSe Hub")
        return None


def _resolve_xml_bytes(issue: NfIssue) -> bytes | None:
    raw = issue.focus_status_raw or {}
    inline = raw.get("xml") or raw.get("nfse_xml") or raw.get("xml_nfse")
    if isinstance(inline, str) and "<" in inline:
        return inline.encode("utf-8")
    if isinstance(inline, (bytes, bytearray)):
        return bytes(inline)

    data = _fetch_focus_bytes(
        raw.get("caminho_xml_nota_fiscal")
        or raw.get("url_xml")
        or raw.get("caminho_xml")
        or ""
    )
    if data and (b"<" in data[:200] or len(data) > 40):
        return data
    if _is_focus_stub_mode() and raw.get("provider") != "sefin":
        return _STUB_NFSE_XML
    return None


def _is_focus_stub_mode() -> bool:
    return (getattr(settings, "FOCUS_HTTP_MODE", None) or "stub").lower() != "http"


def _fetch_focus_bytes(path_or_url: str | None) -> bytes | None:
    """Baixa arquivo Focus: URL absoluta S3 ou caminho relativo autenticado."""
    ref = str(path_or_url or "").strip()
    if not ref:
        return None
    url = ref if ref.startswith("http") else _absolute_focus_url(ref)
    if not url:
        return None
    headers = {}
    auth = None
    if not ref.startswith("http"):
        token = getattr(settings, "FOCUS_API_TOKEN", "") or ""
        if token:
            auth = (token, "")
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            response = client.get(url, auth=auth, headers=headers)
            response.raise_for_status()
            return response.content
    except Exception:  # noqa: BLE001 — não falha a autorização por artefato
        logger.exception("Falha ao baixar artefato Focus url=%s", url)
        return None


def _absolute_focus_url(path: str) -> str:
    base = (
        getattr(settings, "FOCUS_API_BASE_URL", None)
        or "https://homologacao.focusnfe.com.br"
    ).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"
