"""Sprint C — multimunicípio: IBGE explícito + import CSV multi-IBGE."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from apps.fiscal.models import MunicipalTaxRule, TaxRuleCatalog
from apps.fiscal.readiness import provider_ibge
from apps.master_data.models import Provider


@dataclass
class CsvImportRow:
    line: int
    service_code: str
    ibge_code: str
    iss_rate: str
    municipio_nome: str = ""
    uf: str = ""


@dataclass
class MultimunicipioImportResult:
    applied_service_codes: list[str] = field(default_factory=list)
    applied_rows: list[dict[str, str]] = field(default_factory=list)
    ibge_codes: list[str] = field(default_factory=list)
    catalog_version: int | None = None
    catalog_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_ibge_code(value: str, *, field_label: str = "IBGE") -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())[:7]
    if len(digits) != 7:
        raise ValueError(
            f"{field_label} deve ter 7 dígitos (código IBGE do município)."
        )
    return digits


def provider_default_ibge(provider: Provider) -> str:
    return provider_ibge(provider)


def resolve_wizard_ibge_code(
    *,
    post_ibge: str,
    provider: Provider,
    required: bool = True,
) -> str:
    """
    IBGE da prestação no wizard:
    1) valor explícito do formulário
    2) endereço do prestador
    """
    explicit = (post_ibge or "").strip()
    if explicit:
        return normalize_ibge_code(explicit, field_label="IBGE município da prestação")
    default = provider_default_ibge(provider)
    if default:
        return default
    if required:
        raise ValueError(
            "Informe o IBGE do município da prestação (7 dígitos) ou cadastre "
            "codigo_ibge no endereço do prestador."
        )
    return ""


def list_published_ibge_codes(*, tenant) -> list[dict[str, str]]:
    """Municípios com ao menos uma regra ISS publicada (para datalist wizard)."""
    catalog = TaxRuleCatalog.objects.filter(
        tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
    ).first()
    if catalog is None:
        return []
    rows = (
        MunicipalTaxRule.objects.filter(tenant=tenant, catalog=catalog)
        .values("ibge_code", "municipio_nome", "uf")
        .distinct()
        .order_by("ibge_code")
    )
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        ibge = (row.get("ibge_code") or "").strip()
        if not ibge or ibge in seen:
            continue
        seen.add(ibge)
        nome = (row.get("municipio_nome") or "").strip()
        uf = (row.get("uf") or "").strip()
        label = f"{ibge} · {nome}/{uf}".strip(" ·/") if nome else ibge
        out.append({"ibge_code": ibge, "label": label})
    return out


def parse_csv_preview(csv_text: str) -> list[CsvImportRow]:
    """Valida cabeçalho e linhas sem publicar (dry-run)."""
    from apps.fiscal.templates_factory import _parse_rules_csv_rows

    return [
        CsvImportRow(
            line=int(r["line"]),
            service_code=r["service_code"],
            ibge_code=r["ibge_code"],
            iss_rate=str(r["iss_rate"]),
            municipio_nome=str(r.get("municipio_nome") or ""),
            uf=str(r.get("uf") or ""),
        )
        for r in _parse_rules_csv_rows(csv_text)
    ]
