"""Seleção do provedor WhatsApp: Evolution (não oficial) ou Meta Cloud API (oficial).

Ordem de resolução: `tenant.settings["whatsapp_provider"]` → `WHATSAPP_PROVIDER` global.
Decisão PO 2026-08-01 (ARD §17): ambos os provedores suportados.
"""

from __future__ import annotations

from typing import Protocol

from django.conf import settings

from integrations.evolution.client import get_evolution_gateway
from integrations.meta_cloud.client import get_meta_cloud_gateway

PROVIDER_EVOLUTION = "evolution"
PROVIDER_META = "meta"


class WhatsAppGateway(Protocol):
    def send_text(self, *, phone_e164: str, text: str) -> dict: ...

    def send_media(
        self,
        *,
        phone_e164: str,
        filename: str,
        mime_type: str,
        data: bytes,
        caption: str = "",
    ) -> dict: ...


def resolve_whatsapp_provider(tenant=None) -> str:
    tenant_provider = ""
    if tenant is not None:
        tenant_provider = str(
            (getattr(tenant, "settings", None) or {}).get("whatsapp_provider") or ""
        ).strip().lower()
    provider = tenant_provider or (settings.WHATSAPP_PROVIDER or "").strip().lower()
    if provider == PROVIDER_META:
        return PROVIDER_META
    return PROVIDER_EVOLUTION


def get_whatsapp_gateway(tenant=None) -> WhatsAppGateway:
    if resolve_whatsapp_provider(tenant) == PROVIDER_META:
        return get_meta_cloud_gateway()
    return get_evolution_gateway()
