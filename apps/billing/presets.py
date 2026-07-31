"""Predefinições de cobrança por tenant (layout Inter: agenda / multa% / juros% a.m.)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.billing.exceptions import InvalidBillingPresetError

PRESET_KEY = "billing_preset"
NUM_DIAS_AGENDA_MAX = 60
PERCENT_MAX = Decimal("100")


def _as_decimal(value, *, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidBillingPresetError(f"{field} inválido") from exc


def default_billing_preset() -> dict:
    return {
        "num_dias_agenda": 0,
        "apply_multa": False,
        "multa_percent": "0",
        "apply_mora": False,
        "mora_percent_am": "0",
    }


def normalize_billing_preset(raw: dict | None) -> dict:
    base = default_billing_preset()
    data = dict(raw or {})
    num = int(data.get("num_dias_agenda", base["num_dias_agenda"]) or 0)
    if num < 0 or num > NUM_DIAS_AGENDA_MAX:
        raise InvalidBillingPresetError(
            f"num_dias_agenda deve estar entre 0 e {NUM_DIAS_AGENDA_MAX}"
        )

    apply_multa = bool(data.get("apply_multa", base["apply_multa"]))
    multa = _as_decimal(
        data.get("multa_percent", base["multa_percent"]),
        field="multa_percent",
    )
    if multa < 0 or multa > PERCENT_MAX:
        raise InvalidBillingPresetError("multa_percent deve estar entre 0 e 100")
    if apply_multa and multa <= 0:
        raise InvalidBillingPresetError("multa_percent deve ser > 0 quando apply_multa")

    apply_mora = bool(data.get("apply_mora", base["apply_mora"]))
    mora = _as_decimal(
        data.get("mora_percent_am", base["mora_percent_am"]),
        field="mora_percent_am",
    )
    if mora < 0 or mora > PERCENT_MAX:
        raise InvalidBillingPresetError("mora_percent_am deve estar entre 0 e 100")
    if apply_mora and mora <= 0:
        raise InvalidBillingPresetError(
            "mora_percent_am deve ser > 0 quando apply_mora"
        )

    return {
        "num_dias_agenda": num,
        "apply_multa": apply_multa,
        "multa_percent": str(multa.normalize()),
        "apply_mora": apply_mora,
        "mora_percent_am": str(mora.normalize()),
    }


def get_billing_preset(*, tenant) -> dict:
    settings_map = tenant.settings or {}
    raw = settings_map.get(PRESET_KEY)
    if not isinstance(raw, dict):
        return default_billing_preset()
    try:
        return normalize_billing_preset(raw)
    except InvalidBillingPresetError:
        return default_billing_preset()


@transaction.atomic
def set_billing_preset(*, tenant, preset: dict) -> dict:
    normalized = normalize_billing_preset(preset)
    settings_map = dict(tenant.settings or {})
    settings_map[PRESET_KEY] = normalized
    tenant.settings = settings_map
    tenant.save(update_fields=["settings", "updated_at"])
    return normalized


def resolve_charge_options_from_preset(preset: dict) -> dict:
    """Snapshot aplicado na emissão Inter (multa só %, mora % a.m.)."""
    options: dict = {
        "num_dias_agenda": int(preset.get("num_dias_agenda") or 0),
        "multa_percent": None,
        "mora_percent_am": None,
    }
    if preset.get("apply_multa"):
        options["multa_percent"] = float(Decimal(str(preset["multa_percent"])))
    if preset.get("apply_mora"):
        options["mora_percent_am"] = float(Decimal(str(preset["mora_percent_am"])))
    return options
