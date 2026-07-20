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

# PDF mínimo quando Focus stub não devolve URL (dev/QA offline).
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


def ensure_authorized_artifacts(issue: NfIssue) -> list[NfArtifact]:
    """Garante NfArtifact PDF + XML após autorização. Idempotente por kind."""
    issue.refresh_from_db()
    if issue.status != NfIssue.Status.AUTHORIZED:
        return []

    created: list[NfArtifact] = []
    pdf = _ensure_kind(
        issue,
        kind=NfArtifact.Kind.PDF,
        purpose="nf_pdf",
        filename_prefix="danfse",
        extension="pdf",
        content_type="application/pdf",
        data=_resolve_danfse_bytes(issue),
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
        data=_resolve_xml_bytes(issue),
    )
    if xml:
        created.append(xml)
    return created


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


def _resolve_danfse_bytes(issue: NfIssue) -> bytes | None:
    raw = issue.focus_status_raw or {}
    data = _fetch_focus_bytes(
        raw.get("url_danfse")
        or raw.get("caminho_danfse")
        or raw.get("url_pdf")
        or ""
    )
    if data and (data.startswith(b"%PDF") or len(data) > 100):
        return data
    if _is_stub_mode():
        return _STUB_DANFSE_PDF
    return None


def _resolve_xml_bytes(issue: NfIssue) -> bytes | None:
    raw = issue.focus_status_raw or {}
    data = _fetch_focus_bytes(
        raw.get("caminho_xml_nota_fiscal")
        or raw.get("url_xml")
        or raw.get("caminho_xml")
        or ""
    )
    if data and (b"<" in data[:200] or len(data) > 40):
        return data
    if _is_stub_mode():
        return _STUB_NFSE_XML
    return None


def _is_stub_mode() -> bool:
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
