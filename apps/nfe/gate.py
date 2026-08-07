"""Gate T0 + config de série NF-e (LLR D-06 / API §8) — sem SEFAZ."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction

from apps.accounts.certificates import get_primary_certificate
from apps.master_data.models import Provider
from apps.nfe.models import NfeNumberSeries
from apps.nfe.services import nfe_feature_enabled
from integrations.sefaz_nfe.endpoints import list_supported_ufs


def default_tp_amb() -> str:
    return str(getattr(settings, "NFE_DEFAULT_TP_AMB", "2") or "2")[:1]


def default_series() -> int:
    return 1


def http_mode() -> str:
    return (getattr(settings, "NFE_HTTP_MODE", "stub") or "stub").lower()


def _provider_uf(addr: dict | None) -> str:
    if not isinstance(addr, dict):
        return ""
    return str(addr.get("uf") or addr.get("UF") or "").upper().strip()


def list_series_for_tenant(*, tenant, provider: Provider | None = None) -> list[dict[str, Any]]:
    qs = NfeNumberSeries.objects.filter(tenant=tenant).select_related("provider")
    if provider is not None:
        qs = qs.filter(provider=provider)
    qs = qs.order_by("provider_id", "series", "tp_amb")
    return [
        {
            "id": str(row.id),
            "provider_id": str(row.provider_id),
            "provider_document": row.provider.document if row.provider_id else "",
            "series": row.series,
            "tp_amb": row.tp_amb,
            "next_number": row.next_number,
            "is_active": row.is_active,
        }
        for row in qs
    ]


@transaction.atomic
def upsert_number_series(
    *,
    tenant,
    provider: Provider,
    series: int = 1,
    tp_amb: str | None = None,
    next_number: int | None = None,
    is_active: bool = True,
) -> NfeNumberSeries:
    if provider.tenant_id != tenant.id:
        raise ValueError("provider de outro tenant")
    amb = (tp_amb or default_tp_amb())[:1]
    if amb not in {"1", "2"}:
        raise ValueError("tp_amb deve ser 1 ou 2")
    ser = max(1, int(series or 1))
    row, created = NfeNumberSeries.objects.select_for_update().get_or_create(
        tenant=tenant,
        provider=provider,
        series=ser,
        tp_amb=amb,
        defaults={
            "next_number": max(1, int(next_number or 1)),
            "is_active": is_active,
        },
    )
    updates: list[str] = []
    if next_number is not None:
        n = max(1, int(next_number))
        if not created and n < row.next_number:
            # operador pode baixar só se ainda não usou (igual: next); bloqueio fraco
            raise ValueError(
                f"next_number={n} menor que contador atual {row.next_number}; "
                "não regrida sem processo de inutilização"
            )
        if n != row.next_number:
            row.next_number = n
            updates.append("next_number")
    if row.is_active != bool(is_active):
        row.is_active = bool(is_active)
        updates.append("is_active")
    if updates:
        updates.append("updated_at")
        row.save(update_fields=updates)
    return row


def estimated_next_number(
    *,
    tenant,
    provider: Provider,
    series: int | None = None,
    tp_amb: str | None = None,
) -> tuple[int, NfeNumberSeries | None]:
    ser = series if series is not None else default_series()
    amb = (tp_amb or default_tp_amb())[:1]
    row = (
        NfeNumberSeries.objects.filter(
            tenant=tenant,
            provider=provider,
            series=ser,
            tp_amb=amb,
            is_active=True,
        )
        .order_by("id")
        .first()
    )
    if row is None:
        return 1, None
    return int(row.next_number), row


def build_gate_payload(
    *,
    tenant,
    provider_id: str | None = None,
    series: int | None = None,
    tp_amb: str | None = None,
) -> dict[str, Any]:
    enabled = nfe_feature_enabled()
    mode = http_mode()
    ser = series if series is not None else default_series()
    amb = (tp_amb or default_tp_amb())[:1]
    checks: list[dict[str, Any]] = [
        {"id": "nfe_enabled", "ok": enabled, "label": "NFE_ENABLED", "must": True},
    ]

    providers = list(
        Provider.objects.filter(tenant=tenant, is_active=True).order_by("created_at")
    )
    provider: Provider | None = None
    if provider_id:
        provider = next((p for p in providers if str(p.id) == str(provider_id)), None)
        if provider is None:
            provider = Provider.objects.filter(
                tenant=tenant, id=provider_id, is_active=True
            ).first()
    if provider is None and providers:
        provider = providers[0]

    next_estimated: int | None = None
    if provider is None:
        checks.append(
            {"id": "provider", "ok": False, "label": "Nenhum prestador ativo", "must": True}
        )
    else:
        addr = provider.address or {}
        uf = _provider_uf(addr if isinstance(addr, dict) else {})
        ie = (provider.state_registration or "").strip()
        checks.append(
            {
                "id": "provider",
                "ok": True,
                "label": f"Emitente {provider.document}",
                "must": True,
            }
        )
        checks.append(
            {
                "id": "uf",
                "ok": bool(uf),
                "label": f"UF emitente={uf or '—'}",
                "must": True,
            }
        )
        ie_ok = bool(ie) or mode == "stub"
        checks.append(
            {
                "id": "ie",
                "ok": ie_ok,
                "label": (
                    f"IE={'ok' if ie else 'pendente'}"
                    + ("" if ie else " (ok em stub)" if mode == "stub" else " obrigatória em http")
                ),
                "must": True,
            }
        )
        cert = get_primary_certificate(tenant=tenant, cnpj=provider.document)
        cert_ok = cert is not None or mode == "stub"
        checks.append(
            {
                "id": "cert",
                "ok": cert_ok,
                "label": (
                    f"Cert A1 {cert.status}"
                    if cert
                    else (
                        "Cert A1 ausente (ok em stub)"
                        if mode == "stub"
                        else "Cert A1 ausente"
                    )
                ),
                "must": True,
            }
        )
        next_estimated, series_row = estimated_next_number(
            tenant=tenant, provider=provider, series=ser, tp_amb=amb
        )
        series_exists = series_row is not None
        # stub: auto-seed no emit; http: exige série cadastrada explicitamente
        series_ok = series_exists or mode == "stub"
        checks.append(
            {
                "id": "series",
                "ok": series_ok,
                "label": (
                    f"Série {ser}/{amb} · próximo estimado {next_estimated}"
                    if series_exists
                    else (
                        f"Série {ser}/{amb} será auto-criada (stub) · próximo estimado 1"
                        if mode == "stub"
                        else f"Série {ser}/{amb} não cadastrada — use PUT /nfe/config/"
                    )
                ),
                "must": True,
            }
        )

    must_ok = all(c["ok"] for c in checks if c.get("must"))
    can_create = bool(enabled and must_ok)

    return {
        "enabled": enabled,
        "can_create": can_create,
        "checks": checks,
        "http_mode": mode,
        "pivot_uf": getattr(settings, "NFE_PIVOT_UF", "SP"),
        "supported_ufs": list_supported_ufs(),
        "provider_id": str(provider.id) if provider else None,
        "series": ser,
        "tp_amb": amb,
        "next_number_estimated": next_estimated,
        "series_rows": list_series_for_tenant(tenant=tenant, provider=provider)
        if provider
        else list_series_for_tenant(tenant=tenant),
    }


def build_config_payload(*, tenant, provider_id: str | None = None) -> dict[str, Any]:
    gate = build_gate_payload(tenant=tenant, provider_id=provider_id)
    return {
        "enabled": gate["enabled"],
        "http_mode": gate["http_mode"],
        "pivot_uf": gate["pivot_uf"],
        "default_series": default_series(),
        "default_tp_amb": default_tp_amb(),
        "supported_ufs": gate["supported_ufs"],
        "provider_id": gate["provider_id"],
        "series": gate["series_rows"],
        "gate": {
            "can_create": gate["can_create"],
            "checks": gate["checks"],
            "next_number_estimated": gate["next_number_estimated"],
        },
    }
