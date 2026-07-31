from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from django.conf import settings

LAYOUT_NFSE = "nfse"
LAYOUT_NFSEN = "nfsen"
LAYOUT_BETHA = "betha_soap"
LAYOUT_SEFIN = "sefin"

ATIBAIA_IBGE = "3504107"
SIMPLES_REGIMES = frozenset({"simples_nacional", "simples"})
SEFIN_KINDS = frozenset({"sefin", "exeq_nacional"})


@dataclass(frozen=True)
class EmissionRoute:
    kind: str
    layout: str


def _csv_codes(setting_name: str) -> frozenset[str]:
    raw = getattr(settings, setting_name, "") or ""
    return frozenset(code.strip() for code in raw.split(",") if code.strip())


def _betha_ibge_codes() -> frozenset[str]:
    return _csv_codes("NFSE_BETHA_IBGE_CODES")


def _national_ibge_codes() -> frozenset[str]:
    codes = _csv_codes("NFSE_NATIONAL_IBGE_CODES")
    return codes if codes else frozenset({ATIBAIA_IBGE})


def _default_provider_kind() -> str:
    kind = (getattr(settings, "NFSE_DEFAULT_PROVIDER", None) or "sefin").lower().strip()
    if kind in SEFIN_KINDS:
        return "sefin"
    if kind == "betha":
        return "betha"
    return "focus"


def _tenant_focus_layout(tenant_settings: dict | None, focus_layout: str | None) -> str:
    layout = (
        focus_layout
        or getattr(settings, "NFSE_DEFAULT_LAYOUT", LAYOUT_NFSEN)
        or LAYOUT_NFSEN
    )
    layout = str(layout).lower().strip()
    return layout if layout in {LAYOUT_NFSE, LAYOUT_NFSEN} else LAYOUT_NFSEN


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def simples_must_use_nfsen(*, tax_regime: str | None, competence_date) -> bool:
    """Simples Nacional → NFS-e Nacional a partir de NFSE_NATIONAL_MANDATORY_FROM."""
    if not tax_regime:
        return False
    if str(tax_regime).lower().strip() not in SIMPLES_REGIMES:
        return False
    competence = _as_date(competence_date)
    if competence is None:
        return False
    raw = getattr(settings, "NFSE_NATIONAL_MANDATORY_FROM", "2026-09-01") or "2026-09-01"
    cutoff = date.fromisoformat(str(raw)[:10])
    return competence >= cutoff


def _national_route() -> EmissionRoute:
    kind = _default_provider_kind()
    if kind == "sefin":
        return EmissionRoute(kind="sefin", layout=LAYOUT_SEFIN)
    return EmissionRoute(kind="focus", layout=LAYOUT_NFSEN)


def resolve_emission_route(
    *,
    ibge_code: str,
    tenant_settings: dict | None = None,
    focus_layout: str | None = None,
    tax_regime: str | None = None,
    competence_date=None,
) -> EmissionRoute:
    """EmissionRouter — Nacional MVP = sefin (RF-51); Focus só com override lab."""
    if simples_must_use_nfsen(tax_regime=tax_regime, competence_date=competence_date):
        return _national_route()

    settings_map = tenant_settings or {}
    provider_overrides = settings_map.get("nfse_provider_by_ibge") or {}
    layout_overrides = settings_map.get("nfse_layout_by_ibge") or {}
    national = _national_ibge_codes()
    betha = _betha_ibge_codes()
    tenant_layout = _tenant_focus_layout(settings_map, focus_layout)

    if ibge_code in provider_overrides:
        kind = str(provider_overrides[ibge_code]).lower()
        if kind == "betha":
            return EmissionRoute(kind="betha", layout=LAYOUT_BETHA)
        if kind in SEFIN_KINDS:
            return EmissionRoute(kind="sefin", layout=LAYOUT_SEFIN)
        layout = layout_overrides.get(ibge_code) or tenant_layout
        if layout not in {LAYOUT_NFSE, LAYOUT_NFSEN}:
            layout = LAYOUT_NFSEN
        return EmissionRoute(kind="focus", layout=layout)

    if ibge_code in betha and ibge_code not in national:
        return EmissionRoute(kind="betha", layout=LAYOUT_BETHA)

    if ibge_code in national or tenant_layout == LAYOUT_NFSEN:
        return _national_route()

    # Municipal legado Focus (fora do MVP Nacional; lab)
    return EmissionRoute(
        kind="focus",
        layout=layout_overrides.get(ibge_code) or LAYOUT_NFSE,
    )
