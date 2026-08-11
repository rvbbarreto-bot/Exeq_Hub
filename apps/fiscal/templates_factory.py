"""N2 — templates municipais e import CSV (linha a linha, sem alíquota coringa)."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.fiscal.bootstrap import ensure_published_rule
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.master_data.models import TaxRegime

# Templates embutidos: cada item é uma linha fiscal explícita (N2 / anti-N3).
BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "atibaia-sn-v1": {
        "name": "Atibaia SN v1 (lab EXEQ)",
        "ibge_code": "3504107",
        "municipio_nome": "Atibaia",
        "uf": "SP",
        "tax_regime": TaxRegime.SIMPLES,
        "valid_from": date(2024, 1, 1),
        "rules": [
            {
                "service_code": "01.07",
                "iss_rate": Decimal("0.0200"),
                "simples_codigo_tributacao": 3,
            },
            {
                "service_code": "17.01",
                "iss_rate": Decimal("0.0200"),
                "simples_codigo_tributacao": 3,
            },
            {
                "service_code": "17.19",
                "iss_rate": Decimal("0.0200"),
                "simples_codigo_tributacao": 3,
            },
            {
                "service_code": "14.01",
                "iss_rate": Decimal("0.0200"),
                "simples_codigo_tributacao": 3,
            },
        ],
    }
}


def list_templates() -> list[dict[str, Any]]:
    out = []
    for tid, spec in BUILTIN_TEMPLATES.items():
        out.append(
            {
                "id": tid,
                "name": spec["name"],
                "ibge_code": spec["ibge_code"],
                "municipio_nome": spec["municipio_nome"],
                "uf": spec["uf"],
                "tax_regime": spec["tax_regime"],
                "service_codes": [r["service_code"] for r in spec["rules"]],
            }
        )
    return out


def _source_overrides(*, kind: str, ref: str) -> dict:
    return {
        "exeq_source": {
            "kind": kind,
            "ref": ref,
            "adr": "ADR-FISCAL-001",
        }
    }


def _publish_rule_with_source(
    *,
    tenant,
    profile: FiscalProfile,
    ibge: str,
    municipio_nome: str,
    uf: str,
    service_code: str,
    iss_rate: Decimal,
    simples_codigo_tributacao: int | None,
    valid_from: date,
    source_kind: str,
    source_ref: str,
) -> TaxRuleCatalog:
    catalog = ensure_published_rule(
        tenant=tenant,
        profile=profile,
        ibge=ibge,
        municipio_nome=municipio_nome,
        uf=uf,
        service_code=service_code,
        tax_regime=profile.tax_regime,
        iss_rate=iss_rate,
        simples_codigo_tributacao=simples_codigo_tributacao,
        valid_from=valid_from,
    )
    # Anexa origem na linha recém-publicada (N2 audit).
    rule = MunicipalTaxRule.objects.filter(
        tenant=tenant,
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="".join(ch for ch in ibge if ch.isdigit())[:7],
        service_code=service_code.strip(),
        tax_regime=profile.tax_regime,
    ).first()
    if rule is not None:
        meta = dict(rule.focus_field_overrides or {})
        meta.update(_source_overrides(kind=source_kind, ref=source_ref))
        rule.focus_field_overrides = meta
        rule.save(update_fields=["focus_field_overrides", "updated_at"])
    return catalog


def apply_template(
    *,
    tenant,
    profile: FiscalProfile,
    template_id: str,
    service_codes: list[str] | None = None,
) -> dict[str, Any]:
    spec = BUILTIN_TEMPLATES.get(template_id)
    if spec is None:
        raise ValueError(f"Template desconhecido: {template_id}")
    allowed = {r["service_code"] for r in spec["rules"]}
    if service_codes:
        wanted = {c.strip() for c in service_codes if c and c.strip()}
        unknown = wanted - allowed
        if unknown:
            raise ValueError(
                f"Códigos fora do template {template_id}: {', '.join(sorted(unknown))}"
            )
        rules = [r for r in spec["rules"] if r["service_code"] in wanted]
    else:
        rules = list(spec["rules"])
    if not rules:
        raise ValueError("Nenhuma linha do template selecionada.")

    applied: list[str] = []
    catalog = None
    for row in rules:
        catalog = _publish_rule_with_source(
            tenant=tenant,
            profile=profile,
            ibge=spec["ibge_code"],
            municipio_nome=spec["municipio_nome"],
            uf=spec["uf"],
            service_code=row["service_code"],
            iss_rate=row["iss_rate"],
            simples_codigo_tributacao=row.get("simples_codigo_tributacao"),
            valid_from=spec["valid_from"],
            source_kind="template",
            source_ref=template_id,
        )
        applied.append(row["service_code"])
    return {
        "template_id": template_id,
        "applied_service_codes": applied,
        "catalog_version": catalog.version if catalog else None,
        "catalog_id": str(catalog.id) if catalog else None,
    }


def import_rules_csv(
    *,
    tenant,
    profile: FiscalProfile,
    csv_text: str,
) -> dict[str, Any]:
    """
    CSV headers (obrigatórios): service_code, ibge_code, iss_rate
    Opcionais: municipio_nome, uf, simples_codigo_tributacao, valid_from (YYYY-MM-DD)
    """
    text = (csv_text or "").strip()
    if not text:
        raise ValueError("CSV vazio.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV sem cabeçalho.")
    fields = {h.strip().lower() for h in reader.fieldnames if h}
    required = {"service_code", "ibge_code", "iss_rate"}
    if not required.issubset(fields):
        raise ValueError(
            "CSV deve ter colunas service_code, ibge_code, iss_rate "
            f"(recebido: {', '.join(sorted(fields))})"
        )

    applied: list[str] = []
    catalog = None
    for i, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        code = row.get("service_code") or ""
        ibge = row.get("ibge_code") or ""
        if not code and not ibge:
            continue
        try:
            rate = Decimal(row.get("iss_rate", "").replace(",", "."))
        except (InvalidOperation, AttributeError) as exc:
            raise ValueError(f"Linha {i}: iss_rate inválida") from exc
        sn_raw = row.get("simples_codigo_tributacao") or ""
        sn = int(sn_raw) if sn_raw.isdigit() else (
            3 if profile.tax_regime == TaxRegime.SIMPLES else None
        )
        v_from_raw = row.get("valid_from") or "2024-01-01"
        try:
            v_from = date.fromisoformat(v_from_raw)
        except ValueError as exc:
            raise ValueError(f"Linha {i}: valid_from inválido") from exc
        catalog = _publish_rule_with_source(
            tenant=tenant,
            profile=profile,
            ibge=ibge,
            municipio_nome=row.get("municipio_nome") or "Município",
            uf=row.get("uf") or "SP",
            service_code=code,
            iss_rate=rate,
            simples_codigo_tributacao=sn,
            valid_from=v_from,
            source_kind="csv",
            source_ref=f"line:{i}",
        )
        applied.append(code)
    if not applied:
        raise ValueError("Nenhuma linha válida no CSV.")
    return {
        "applied_service_codes": applied,
        "catalog_version": catalog.version if catalog else None,
        "catalog_id": str(catalog.id) if catalog else None,
    }
