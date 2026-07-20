from __future__ import annotations

from django.conf import settings

from apps.accounts.secrets import get_tenant_secret_plaintext
from apps.master_data.models import Provider
from integrations.nfse.empresas import FocusEmpresaClient


def register_provider_on_focus(
    *,
    tenant,
    provider: Provider,
    enable_nfsen_homolog: bool = True,
    enable_nfsen_producao: bool = False,
    webhook_url: str | None = None,
) -> dict:
    token = get_tenant_secret_plaintext(
        tenant=tenant,
        provider="focus",
        key_name="api_token",
    ) or settings.FOCUS_API_TOKEN
    client = FocusEmpresaClient(token=token or "")
    empresa = client.upsert_empresa_from_provider(
        provider,
        enable_nfsen_homolog=enable_nfsen_homolog,
        enable_nfsen_producao=enable_nfsen_producao,
    )
    result: dict = {"empresa": empresa}
    url = webhook_url or getattr(settings, "FOCUS_WEBHOOK_PUBLIC_URL", "") or ""
    if url:
        hook = client.ensure_webhook(
            cnpj=provider.document,
            url=url,
            event="nfsen",
            authorization=getattr(settings, "FOCUS_WEBHOOK_SECRET", "") or None,
        )
        result["webhook"] = hook
    return result
