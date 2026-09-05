"""Gate NFC-e PDV — série mod 65, certificado, CSC (lab)."""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.accounts.certificates import get_primary_certificate
from apps.accounts.models import DigitalCertificate
from apps.master_data.models import Provider
from apps.nfce.models import NfceNumberSeries, TenantCscToken
from apps.nfce.services import nfce_feature_enabled


def default_tp_amb() -> str:
    return str(getattr(settings, "NFCE_DEFAULT_TP_AMB", "2") or "2")[:1]


def default_series() -> int:
    return 1


def http_mode() -> str:
    return (getattr(settings, "NFCE_HTTP_MODE", "stub") or "stub").lower()


def _provider_uf(addr: dict | None) -> str:
    if not isinstance(addr, dict):
        return ""
    return str(addr.get("uf") or addr.get("UF") or "").upper().strip()


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def list_series_for_tenant(*, tenant, provider: Provider | None = None) -> list[dict[str, Any]]:
    qs = NfceNumberSeries.objects.filter(tenant=tenant).select_related("provider")
    if provider is not None:
        qs = qs.filter(provider=provider)
    return [
        {
            "id": str(row.id),
            "provider_id": str(row.provider_id),
            "series": row.series,
            "tp_amb": row.tp_amb,
            "next_number": row.next_number,
            "is_active": row.is_active,
        }
        for row in qs.order_by("provider_id", "series", "tp_amb")
    ]


def estimated_next_number(
    *,
    tenant,
    provider: Provider,
    series: int | None = None,
    tp_amb: str | None = None,
) -> tuple[int, NfceNumberSeries | None]:
    ser = series if series is not None else default_series()
    amb = (tp_amb or default_tp_amb())[:1]
    row = (
        NfceNumberSeries.objects.filter(
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
    enabled = nfce_feature_enabled()
    mode = http_mode()
    ser = series if series is not None else default_series()
    amb = (tp_amb or default_tp_amb())[:1]
    checks: list[dict[str, Any]] = [
        {"id": "nfce_enabled", "ok": enabled, "label": "NFCE_ENABLED", "must": True},
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
            {"id": "provider", "ok": False, "label": "Nenhum emitente ativo", "must": True}
        )
    else:
        addr = provider.address if isinstance(provider.address, dict) else {}
        uf = _provider_uf(addr)
        ibge = _digits(str(addr.get("codigo_ibge") or addr.get("codigo_municipio_ibge") or ""))
        logradouro = str(addr.get("logradouro") or addr.get("street") or "").strip()

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
        checks.append(
            {
                "id": "crt",
                "ok": bool(getattr(provider, "tax_regime", None)),
                "label": f"CRT/regime={provider.tax_regime or '—'}",
                "must": True,
            }
        )
        checks.append(
            {
                "id": "ibge_emit",
                "ok": len(ibge) == 7,
                "label": f"IBGE emitente={ibge or '—'}",
                "must": True,
            }
        )
        checks.append(
            {
                "id": "address_min",
                "ok": bool(logradouro),
                "label": "Endereço emitente (logradouro)"
                if logradouro
                else "Logradouro emitente ausente",
                "must": True,
            }
        )

        cert = get_primary_certificate(tenant=tenant, cnpj=provider.document)
        if mode == "stub":
            cert_ok = True
            cert_label = f"Cert A1 {cert.status}" if cert else "Cert A1 ausente (ok em stub)"
        else:
            usable = {DigitalCertificate.Status.ACTIVE, DigitalCertificate.Status.EXPIRING}
            cert_ok = cert is not None and cert.status in usable
            cert_label = f"Cert A1 {cert.status}" if cert else "Cert A1 ausente"
        checks.append({"id": "cert", "ok": cert_ok, "label": cert_label, "must": True})

        csc = TenantCscToken.objects.filter(
            tenant=tenant, provider=provider, tp_amb=amb, is_active=True
        ).first()
        if mode == "stub":
            csc_ok = True
            csc_label = f"CSC id={csc.csc_id}" if csc else "CSC stub (homolog lab)"
        else:
            csc_ok = csc is not None and bool((csc.csc_token or "").strip())
            if not csc_ok:
                env_token = (getattr(settings, "NFCE_CSC_TOKEN", "") or "").strip()
                csc_ok = bool(env_token)
                csc_label = "CSC via env NFCE_CSC_TOKEN" if csc_ok else "CSC não cadastrado"
            else:
                csc_label = f"CSC id={csc.csc_id}"
        checks.append({"id": "csc", "ok": csc_ok, "label": csc_label, "must": True})

        from apps.nfce.rtc import nfce_rtc_mode

        rtc_mode = nfce_rtc_mode()
        checks.append(
            {
                "id": "rtc",
                "ok": True,
                "label": f"RTC modo={rtc_mode}",
                "must": False,
            }
        )

        next_estimated, series_row = estimated_next_number(
            tenant=tenant, provider=provider, series=ser, tp_amb=amb
        )
        series_ok = series_row is not None or mode == "stub"
        checks.append(
            {
                "id": "series",
                "ok": series_ok,
                "label": (
                    f"Série mod65 {ser}/{amb} · próximo {next_estimated}"
                    if series_row
                    else f"Série {ser}/{amb} auto-criada (stub)"
                ),
                "must": True,
            }
        )

    must_ok = all(c["ok"] for c in checks if c.get("must"))
    return {
        "enabled": enabled,
        "can_create": bool(enabled and must_ok),
        "checks": checks,
        "http_mode": mode,
        "pivot_uf": getattr(settings, "NFE_PIVOT_UF", "SP"),
        "provider_id": str(provider.id) if provider else None,
        "series": ser,
        "tp_amb": amb,
        "next_number_estimated": next_estimated,
        "series_rows": list_series_for_tenant(tenant=tenant, provider=provider)
        if provider
        else list_series_for_tenant(tenant=tenant),
    }


def assert_can_emit(
    *,
    tenant,
    provider: Provider,
    series: int | None = None,
    tp_amb: str | None = None,
) -> None:
    from apps.nfce.exceptions import NfceGateError

    payload = build_gate_payload(
        tenant=tenant,
        provider_id=str(provider.id),
        series=series,
        tp_amb=tp_amb,
    )
    if payload.get("can_create"):
        return
    failed = [
        c for c in payload.get("checks") or [] if c.get("must") and not c.get("ok")
    ]
    raise NfceGateError(json.dumps(failed, ensure_ascii=False))


def build_config_payload(*, tenant, provider_id: str | None = None) -> dict[str, Any]:
    gate = build_gate_payload(tenant=tenant, provider_id=provider_id)
    return {
        "enabled": gate["enabled"],
        "http_mode": gate["http_mode"],
        "default_series": default_series(),
        "default_tp_amb": default_tp_amb(),
        "provider_id": gate["provider_id"],
        "series": gate["series_rows"],
        "gate": {
            "can_create": gate["can_create"],
            "checks": gate["checks"],
            "next_number_estimated": gate["next_number_estimated"],
        },
    }
