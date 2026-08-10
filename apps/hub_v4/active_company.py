"""Empresa ativa (Prestador) na sessão do Hub — contexto multi-CNPJ."""

from __future__ import annotations

from django.http import HttpRequest

from apps.master_data.models import Provider

SESSION_ACTIVE_PROVIDER = "hub_v4_active_provider_id"


def get_active_provider(request: HttpRequest, tenant) -> Provider | None:
    if tenant is None:
        return None
    qs = Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
    if not qs.exists():
        return None

    pid = request.session.get(SESSION_ACTIVE_PROVIDER)
    if pid:
        current = qs.filter(pk=pid).first()
        if current is not None:
            return current

    # Fallback: único prestador, ou o primeiro por razão social
    first = qs.first()
    if first is not None:
        request.session[SESSION_ACTIVE_PROVIDER] = str(first.id)
    return first


def set_active_provider(request: HttpRequest, tenant, provider_id: str | None) -> Provider | None:
    if not provider_id:
        request.session.pop(SESSION_ACTIVE_PROVIDER, None)
        return None
    provider = Provider.objects.filter(
        tenant=tenant, pk=provider_id, is_active=True
    ).first()
    if provider is None:
        return None
    request.session[SESSION_ACTIVE_PROVIDER] = str(provider.id)
    return provider


def clear_active_provider(request: HttpRequest) -> None:
    request.session.pop(SESSION_ACTIVE_PROVIDER, None)
