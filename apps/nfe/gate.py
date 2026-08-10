"""Gate T0 + config de série NF-e (LLR D-06 / API §8) — sem SEFAZ."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.certificates import get_primary_certificate
from apps.accounts.models import DigitalCertificate
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


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


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
    supported = list_supported_ufs()
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
        addr = provider.address if isinstance(provider.address, dict) else {}
        uf = _provider_uf(addr)
        ie = (provider.state_registration or "").strip()
        ie_digits = _digits(ie)
        ie_isento = ie.upper() in {"ISENTO", "ISENTA"}
        ibge = _digits(str(addr.get("codigo_ibge") or addr.get("cMun") or ""))
        logradouro = str(addr.get("logradouro") or addr.get("street") or "").strip()

        checks.append(
            {
                "id": "provider",
                "ok": True,
                "label": f"Emitente {provider.document}",
                "must": True,
            }
        )
        uf_ok = bool(uf)
        checks.append(
            {
                "id": "uf",
                "ok": uf_ok,
                "label": f"UF emitente={uf or '—'}",
                "must": True,
            }
        )
        uf_matrix_ok = (not uf) or (uf in supported)
        checks.append(
            {
                "id": "uf_supported",
                "ok": uf_matrix_ok,
                "label": (
                    f"UF {uf} na matriz U4"
                    if uf and uf_matrix_ok
                    else (f"UF {uf} fora da matriz" if uf else "UF não informada")
                ),
                "must": True,
            }
        )
        # IE: stub aceita vazio; http exige dígitos ou ISENTO
        if mode == "stub":
            ie_ok = True
            ie_label = f"IE={'ok' if ie else 'pendente (ok em stub)'}"
        else:
            ie_ok = ie_isento or len(ie_digits) >= 2
            ie_label = (
                "IE isento"
                if ie_isento
                else (f"IE ok ({len(ie_digits)} dig.)" if ie_ok else "IE pendente/inválida (obrigatória em http)")
            )
        checks.append({"id": "ie", "ok": ie_ok, "label": ie_label, "must": True})

        crt_ok = bool(getattr(provider, "tax_regime", None))
        checks.append(
            {
                "id": "crt",
                "ok": crt_ok,
                "label": f"CRT/regime={provider.tax_regime or '—'}",
                "must": True,
            }
        )
        ibge_ok = len(ibge) == 7
        checks.append(
            {
                "id": "ibge_emit",
                "ok": ibge_ok,
                "label": f"IBGE emitente={ibge or '—'}",
                "must": True,
            }
        )
        addr_ok = bool(logradouro)
        checks.append(
            {
                "id": "address_min",
                "ok": addr_ok,
                "label": "Endereço emitente (logradouro)" if addr_ok else "Logradouro emitente ausente",
                "must": True,
            }
        )

        cert = get_primary_certificate(tenant=tenant, cnpj=provider.document)
        if mode == "stub":
            cert_ok = True
            cert_label = (
                f"Cert A1 {cert.status}" if cert else "Cert A1 ausente (ok em stub)"
            )
        else:
            usable = {
                DigitalCertificate.Status.ACTIVE,
                DigitalCertificate.Status.EXPIRING,
            }
            cert_ok = cert is not None and cert.status in usable
            cert_label = (
                f"Cert A1 {cert.status}"
                if cert
                else "Cert A1 ausente"
            )
            if cert and cert.status not in usable:
                cert_label = f"Cert A1 inutilizável ({cert.status})"
        checks.append({"id": "cert", "ok": cert_ok, "label": cert_label, "must": True})

        # warning < 30d (must=false)
        cert_expiring = False
        if cert and cert.status == DigitalCertificate.Status.EXPIRING:
            cert_expiring = True
        elif cert and getattr(cert, "not_after", None):
            try:
                delta = cert.not_after - timezone.now()
                cert_expiring = 0 < delta.days <= 30
            except Exception:  # noqa: BLE001
                cert_expiring = False
        checks.append(
            {
                "id": "cert_expiring",
                "ok": not cert_expiring,
                "label": "Cert A1 expira em ≤30d" if cert_expiring else "Cert A1 prazo ok",
                "must": False,
            }
        )

        # CNPJ cert == provider (quando cert existe)
        if cert is not None:
            cert_cnpj = _digits(cert.cnpj)
            prov_cnpj = _digits(provider.document)
            cnpj_ok = cert_cnpj == prov_cnpj and len(prov_cnpj) == 14
            checks.append(
                {
                    "id": "cnpj_cert",
                    "ok": cnpj_ok,
                    "label": "CNPJ cert = emitente" if cnpj_ok else "CNPJ cert ≠ emitente",
                    "must": mode != "stub",
                }
            )

        next_estimated, series_row = estimated_next_number(
            tenant=tenant, provider=provider, series=ser, tp_amb=amb
        )
        series_exists = series_row is not None
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
        "supported_ufs": supported,
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
