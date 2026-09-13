"""Resolução CSC (QR Code NFC-e) — tenant DB ou env lab."""

from __future__ import annotations

from django.conf import settings

from apps.nfce.models import TenantCscToken


def normalize_csc_id(raw: str) -> str:
    """Id CSC sem zeros à esquerda (NT QR Code v2)."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if not digits:
        return "1"
    return str(int(digits))


def resolve_csc(*, tenant, provider, tp_amb: str) -> tuple[str, str]:
    amb = str(tp_amb or "2").strip()[:1] or "2"
    row = (
        TenantCscToken.objects.filter(
            tenant=tenant,
            provider=provider,
            tp_amb=amb,
            is_active=True,
        )
        .order_by("-updated_at")
        .first()
    )
    if row and row.csc_token:
        return normalize_csc_id(row.csc_id), str(row.csc_token).strip()

    env_id = normalize_csc_id(getattr(settings, "NFCE_CSC_ID", "1") or "1")
    env_token = (getattr(settings, "NFCE_CSC_TOKEN", "") or "").strip()
    if not env_token:
        mode = (getattr(settings, "NFCE_HTTP_MODE", "stub") or "stub").lower()
        if mode != "http":
            env_token = "HOMOLOGCSC"
    return env_id, env_token
