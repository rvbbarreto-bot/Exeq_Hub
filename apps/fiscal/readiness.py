"""N1 — readiness fiscal / cobertura ISS (fail closed antes da emissão)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.master_data.models import Provider, ServiceCatalogItem


class FiscalReadinessError(ValueError):
    """Configuração incompleta para emitir NFS-e com segurança fiscal."""


@dataclass
class ReadinessCheck:
    code: str
    ok: bool
    label: str
    detail: str = ""


@dataclass
class CoverageCell:
    service_code: str
    service_description: str
    ibge_code: str
    profile_name: str
    tax_regime: str
    ok: bool
    rule_id: str = ""


@dataclass
class FiscalReadiness:
    tenant_id: str
    ready: bool
    checks: list[ReadinessCheck] = field(default_factory=list)
    missing_coverage: list[CoverageCell] = field(default_factory=list)
    coverage: list[CoverageCell] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "ready": self.ready,
            "checks": [asdict(c) for c in self.checks],
            "missing_coverage": [asdict(c) for c in self.missing_coverage],
            "coverage": [asdict(c) for c in self.coverage],
        }


def provider_ibge(provider: Provider) -> str:
    addr = provider.address if isinstance(provider.address, dict) else {}
    raw = (
        addr.get("codigo_ibge")
        or addr.get("codigo_municipio_ibge")
        or addr.get("cMun")
        or ""
    )
    digits = "".join(ch for ch in str(raw) if ch.isdigit())[:7]
    return digits


def published_catalog(*, tenant) -> TaxRuleCatalog | None:
    return TaxRuleCatalog.objects.filter(
        tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
    ).first()


def has_published_rule(
    *,
    tenant,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    service_code: str,
    competence_date: date | None = None,
) -> MunicipalTaxRule | None:
    catalog = published_catalog(tenant=tenant)
    if catalog is None:
        return None
    ibge = "".join(ch for ch in (ibge_code or "") if ch.isdigit())[:7]
    code = (service_code or "").strip()
    if len(ibge) != 7 or not code:
        return None
    day = competence_date or date.today()
    qs = MunicipalTaxRule.objects.filter(
        tenant=tenant,
        catalog=catalog,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge,
        service_code=code,
        tax_regime=fiscal_profile.tax_regime,
        valid_from__lte=day,
    )
    # valid_to null or >= day
    from django.db.models import Q

    return (
        qs.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .order_by("priority", "-valid_from")
        .first()
    )


def assert_emit_rule_cover(
    *,
    tenant,
    fiscal_profile: FiscalProfile | None,
    ibge_code: str,
    service_code: str,
    competence_date: date | None = None,
) -> MunicipalTaxRule:
    if fiscal_profile is None:
        raise FiscalReadinessError(
            "Cadastre um perfil fiscal antes de emitir (N1 go-live)."
        )
    rule = has_published_rule(
        tenant=tenant,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge_code,
        service_code=service_code,
        competence_date=competence_date,
    )
    if rule is None:
        ibge = "".join(ch for ch in (ibge_code or "") if ch.isdigit())[:7] or "—"
        code = (service_code or "").strip() or "—"
        raise FiscalReadinessError(
            f"Sem regra ISS publicada para serviço {code} no município IBGE {ibge} "
            f"(perfil {fiscal_profile.name}). Complete a matriz fiscal em "
            f"Fiscal → Pronto para emitir ou Regras ISS."
        )
    return rule


def coverage_matrix(
    *,
    tenant,
    providers: list[Provider] | None = None,
    services: list[ServiceCatalogItem] | None = None,
    profiles: list[FiscalProfile] | None = None,
    competence_date: date | None = None,
) -> list[CoverageCell]:
    day = competence_date or date.today()
    providers = providers or list(
        Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
    )
    services = services or list(
        ServiceCatalogItem.objects.filter(tenant=tenant, is_active=True).order_by(
            "service_code"
        )
    )
    profiles = profiles or list(
        FiscalProfile.objects.filter(tenant=tenant, status="active").order_by("name")
    )
    if not profiles:
        profiles = list(FiscalProfile.objects.filter(tenant=tenant).order_by("name")[:5])

    cells: list[CoverageCell] = []
    ibges: list[tuple[str, Provider]] = []
    for p in providers:
        ibge = provider_ibge(p)
        if ibge:
            ibges.append((ibge, p))
    # sem provider com IBGE: ainda mostra serviços sem município
    if not ibges:
        for svc in services:
            for prof in profiles:
                cells.append(
                    CoverageCell(
                        service_code=svc.service_code,
                        service_description=svc.description or "",
                        ibge_code="",
                        profile_name=prof.name,
                        tax_regime=prof.tax_regime,
                        ok=False,
                    )
                )
        return cells

    for ibge, _prov in ibges:
        for svc in services:
            for prof in profiles:
                rule = has_published_rule(
                    tenant=tenant,
                    fiscal_profile=prof,
                    ibge_code=ibge,
                    service_code=svc.service_code,
                    competence_date=day,
                )
                cells.append(
                    CoverageCell(
                        service_code=svc.service_code,
                        service_description=svc.description or "",
                        ibge_code=ibge,
                        profile_name=prof.name,
                        tax_regime=prof.tax_regime,
                        ok=rule is not None,
                        rule_id=str(rule.id) if rule else "",
                    )
                )
    return cells


def fiscal_readiness(
    *,
    tenant,
    provider: Provider | None = None,
    competence_date: date | None = None,
) -> FiscalReadiness:
    checks: list[ReadinessCheck] = []
    providers = list(
        Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
    )
    if provider is not None:
        providers = [provider] if provider in providers or provider.pk else [provider]

    checks.append(
        ReadinessCheck(
            code="provider",
            ok=bool(providers),
            label="Prestador (CNPJ) ativo",
            detail=f"{len(providers)} prestador(es)" if providers else "Nenhum",
        )
    )

    with_ibge = [p for p in providers if provider_ibge(p)]
    checks.append(
        ReadinessCheck(
            code="provider_ibge",
            ok=bool(with_ibge) if providers else False,
            label="IBGE no endereço do prestador",
            detail=(
                ", ".join(sorted({provider_ibge(p) for p in with_ibge}))
                if with_ibge
                else "Informe codigo_ibge no endereço da empresa"
            ),
        )
    )

    profiles = list(
        FiscalProfile.objects.filter(tenant=tenant, status="active").order_by("name")
    )
    checks.append(
        ReadinessCheck(
            code="fiscal_profile",
            ok=bool(profiles),
            label="Perfil fiscal ativo",
            detail=", ".join(p.name for p in profiles) if profiles else "Cadastre um perfil",
        )
    )

    services = list(
        ServiceCatalogItem.objects.filter(tenant=tenant, is_active=True).order_by(
            "service_code"
        )
    )
    checks.append(
        ReadinessCheck(
            code="services",
            ok=bool(services),
            label="Serviços ativos no portfólio",
            detail=f"{len(services)} serviço(s)" if services else "Cadastre serviços",
        )
    )

    catalog = published_catalog(tenant=tenant)
    checks.append(
        ReadinessCheck(
            code="catalog",
            ok=catalog is not None,
            label="Catálogo de regras ISS publicado",
            detail=f"v{catalog.version}" if catalog else "Publique ao menos uma regra",
        )
    )

    cells = coverage_matrix(
        tenant=tenant,
        providers=providers,
        services=services,
        profiles=profiles,
        competence_date=competence_date,
    )
    # Cobertura “pronto”: cada (serviço × IBGE do prestador) precisa de regra em
    # pelo menos um perfil ativo (senão a matriz marca ok=False em todas as linhas).
    missing = [c for c in cells if not c.ok]
    # pronto operacional: existe ao menos um caminho (serviço+ibge+perfil) completo
    # e nenhum serviço do portfólio fica sem regra em todos os perfis para um IBGE
    by_key: dict[tuple[str, str], list[CoverageCell]] = {}
    for c in cells:
        if not c.ibge_code:
            continue
        by_key.setdefault((c.service_code, c.ibge_code), []).append(c)
    uncovered_pairs = [
        key for key, rows in by_key.items() if not any(r.ok for r in rows)
    ]
    matrix_ok = bool(by_key) and not uncovered_pairs and not any(
        c for c in cells if not c.ibge_code
    )
    checks.append(
        ReadinessCheck(
            code="coverage",
            ok=matrix_ok,
            label="Matriz ISS (serviço × município do prestador)",
            detail=(
                "Cobertura completa"
                if matrix_ok
                else f"{len(uncovered_pairs)} par(es) sem regra — ver matriz"
            ),
        )
    )

    ready = all(c.ok for c in checks)
    return FiscalReadiness(
        tenant_id=str(tenant.id),
        ready=ready,
        checks=checks,
        missing_coverage=missing,
        coverage=cells,
    )
