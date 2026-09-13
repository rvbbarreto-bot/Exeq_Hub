"""Logo emitente para DANFE — resolução a partir do cadastro Provider."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from apps.master_data.models import Provider


def resolve_provider_logo_bytes(provider: Provider | None) -> bytes | None:
    """Lê logo PNG/JPG do endereço JSON ou diretório configurado por CNPJ."""
    if provider is None:
        return None
    addr = provider.address if isinstance(provider.address, dict) else {}
    custom = (addr.get("danfe_logo_path") or addr.get("logo_path") or "").strip()
    if custom:
        path = Path(custom)
        if path.is_file():
            return path.read_bytes()
    logo_dir = (getattr(settings, "NFE_DANFE_LOGO_DIR", "") or "").strip()
    if not logo_dir:
        return None
    cnpj = "".join(ch for ch in str(provider.document or "") if ch.isdigit())
    if len(cnpj) != 14:
        return None
    base = Path(logo_dir)
    for ext in ("png", "jpg", "jpeg", "webp"):
        candidate = base / f"{cnpj}.{ext}"
        if candidate.is_file():
            return candidate.read_bytes()
    return None
