"""IBPT — tributos aproximados (Lei 12.741) para vTotTrib."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings


def ibpt_enabled() -> bool:
    return bool(getattr(settings, "IBPT_ENABLED", False))


def _data_path() -> Path | None:
    raw = getattr(settings, "IBPT_DATA_PATH", "") or ""
    path = Path(raw) if raw else None
    if path and path.is_file():
        return path
    return None


@lru_cache(maxsize=1)
def _load_rates() -> dict[tuple[str, str], dict[str, Decimal]]:
    """Chave (ncm, uf) → {fed, est, mun} percentuais."""
    path = _data_path()
    if path is None:
        return {}
    rates: dict[tuple[str, str], dict[str, Decimal]] = {}
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload if isinstance(payload, list) else payload.get("rows", []):
            ncm = str(row.get("ncm", "")).zfill(8)[:8]
            uf = str(row.get("uf", "")).upper()[:2]
            if len(ncm) != 8 or not uf:
                continue
            rates[(ncm, uf)] = {
                "fed": Decimal(str(row.get("fed_pct", 0))),
                "est": Decimal(str(row.get("est_pct", 0))),
                "mun": Decimal(str(row.get("mun_pct", 0))),
            }
        return rates
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ncm = str(row.get("ncm", "")).zfill(8)[:8]
            uf = str(row.get("uf", "")).upper()[:2]
            if len(ncm) != 8 or not uf:
                continue
            rates[(ncm, uf)] = {
                "fed": Decimal(str(row.get("fed_pct", 0))),
                "est": Decimal(str(row.get("est_pct", 0))),
                "mun": Decimal(str(row.get("mun_pct", 0))),
            }
    return rates


def compute_v_tot_trib_cents(
    items: list[dict[str, Any]],
    *,
    emit_uf: str,
) -> int:
    """Soma tributos aproximados por item. Retorna 0 se IBPT desabilitado ou sem dados."""
    if not ibpt_enabled():
        return 0
    rates = _load_rates()
    if not rates:
        return 0
    uf = (emit_uf or "").upper()[:2]
    total = Decimal(0)
    for it in items:
        ncm = str(it.get("ncm") or "").zfill(8)[:8]
        line_cents = int(it.get("total_cents") or 0)
        if line_cents <= 0 or len(ncm) != 8:
            continue
        row = rates.get((ncm, uf))
        if not row:
            continue
        line = Decimal(line_cents) / Decimal(100)
        pct = row["fed"] + row["est"] + row["mun"]
        total += line * pct / Decimal(100)
    return int((total * Decimal(100)).quantize(Decimal("1")))
