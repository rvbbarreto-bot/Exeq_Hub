"""Download de artefatos NFS-e no Hub V4 (mesmo storage do Admin; só UI)."""

from __future__ import annotations

from io import BytesIO

from django.http import FileResponse, Http404, HttpRequest
from django.shortcuts import get_object_or_404

from apps.issuance.models import NfArtifact, NfIssue
from shared.storage import StorageError, get_storage

ALLOWED_KINDS = {
    "pdf": NfArtifact.Kind.PDF,
    "xml": NfArtifact.Kind.XML,
}


def download_nf_artifact(*, tenant, issue_id, kind: str) -> FileResponse:
    kind_key = (kind or "").strip().lower()
    if kind_key not in ALLOWED_KINDS:
        raise Http404("Tipo de documento inválido")
    issue = get_object_or_404(NfIssue, pk=issue_id, tenant=tenant)
    artifact = (
        NfArtifact.objects.filter(
            tenant=tenant,
            nf_issue=issue,
            kind=ALLOWED_KINDS[kind_key],
        )
        .select_related("stored_file")
        .first()
    )
    if artifact is None or artifact.stored_file_id is None:
        raise Http404("Documento ainda não disponível")
    stored = artifact.stored_file
    try:
        data = get_storage().get(key=stored.object_key)
    except StorageError as exc:
        raise Http404(str(exc)) from exc
    ext = kind_key
    ref = (issue.focus_ref or issue.idempotency_key or str(issue.id)[:8]).replace(
        "/", "-"
    )
    filename = f"nfse-{ref}-{kind_key}.{ext}"
    content_type = stored.content_type or (
        "application/pdf" if kind_key == "pdf" else "application/xml"
    )
    return FileResponse(
        BytesIO(data),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )


def artifact_presence(issue: NfIssue) -> dict[str, bool]:
    kinds = set(issue.artifacts.values_list("kind", flat=True))
    return {
        "pdf": NfArtifact.Kind.PDF in kinds,
        "xml": NfArtifact.Kind.XML in kinds,
    }
