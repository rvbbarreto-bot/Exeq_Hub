"""Cursor NSU — get/create com defaults."""

from __future__ import annotations

from django.conf import settings

from apps.accounts.models import Tenant
from apps.master_data.models import Provider
from apps.nfe.entrada.models import NfeDistribuicaoCursor


def _normalize_cnpj(value: str) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())[:14]


def get_or_create_cursor(
    *,
    tenant: Tenant,
    provider: Provider,
    tp_amb: str | None = None,
) -> NfeDistribuicaoCursor:
    cnpj = _normalize_cnpj(provider.document)
    amb = str(tp_amb or getattr(settings, "NFE_DEFAULT_TP_AMB", "2") or "2")[:1]
    cursor, created = NfeDistribuicaoCursor.objects.get_or_create(
        tenant=tenant,
        provider=provider,
        defaults={
            "cnpj": cnpj,
            "ult_nsu": "0",
            "max_nsu": "0",
            "tp_amb": amb if amb in ("1", "2") else "2",
        },
    )
    if not created and cursor.cnpj != cnpj:
        cursor.cnpj = cnpj
        cursor.save(update_fields=["cnpj", "updated_at"])
    return cursor
