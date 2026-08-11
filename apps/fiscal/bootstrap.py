"""Bootstrap de regra municipal publicada (idempotente) — onboarding + Hub."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog


def ensure_published_rule(
    *,
    tenant,
    profile: FiscalProfile,
    ibge: str,
    municipio_nome: str,
    uf: str,
    service_code: str,
    tax_regime: str | None = None,
    iss_rate: Decimal | str = Decimal("0.0200"),
    simples_codigo_tributacao: int | None = 3,
    valid_from: date | None = None,
) -> TaxRuleCatalog:
    """
    Garante regra profile × IBGE × serviço × regime em catálogo publicado.
    Se já existir no catálogo publicado, retorna-o sem alterações.
    Caso contrário copia o publicado (se houver) + delta e publica.
    """
    regime = tax_regime or profile.tax_regime
    ibge_digits = "".join(ch for ch in (ibge or "") if ch.isdigit())[:7]
    if len(ibge_digits) != 7:
        raise ValueError("Informe IBGE com 7 dígitos.")
    code = (service_code or "").strip()
    if not code:
        raise ValueError("Informe o código do serviço para a regra.")
    uf2 = (uf or "").strip().upper()[:2]
    municipio = (municipio_nome or "").strip() or "Município"
    rate = iss_rate if isinstance(iss_rate, Decimal) else Decimal(str(iss_rate))
    v_from = valid_from or date(2024, 1, 1)

    rule_filter = dict(
        tenant=tenant,
        fiscal_profile=profile,
        ibge_code=ibge_digits,
        service_code=code,
        tax_regime=regime,
    )
    published = TaxRuleCatalog.objects.filter(
        tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
    ).first()
    if published is not None:
        if MunicipalTaxRule.objects.filter(catalog=published, **rule_filter).exists():
            return published
        catalog = create_catalog(tenant=tenant)
        for old in MunicipalTaxRule.objects.filter(catalog=published):
            add_rule(
                catalog=catalog,
                fiscal_profile=old.fiscal_profile,
                ibge_code=old.ibge_code,
                municipio_nome=old.municipio_nome,
                uf=old.uf,
                service_code=old.service_code,
                tax_regime=old.tax_regime,
                iss_rate=old.iss_rate,
                irrf_rate=old.irrf_rate,
                pis_rate=old.pis_rate,
                cofins_rate=old.cofins_rate,
                iss_retained=old.iss_retained,
                simples_codigo_tributacao=old.simples_codigo_tributacao,
                valid_from=old.valid_from,
                valid_to=old.valid_to,
                priority=old.priority,
                focus_field_overrides=old.focus_field_overrides or {},
            )
        add_rule(
            catalog=catalog,
            fiscal_profile=profile,
            ibge_code=ibge_digits,
            municipio_nome=municipio,
            uf=uf2,
            service_code=code,
            tax_regime=regime,
            iss_rate=rate,
            simples_codigo_tributacao=simples_codigo_tributacao,
            valid_from=v_from,
        )
        catalog.publish_checklist = {
            "csv_validated": True,
            "rules_reviewed": True,
            "terms_accepted": True,
        }
        catalog.save(update_fields=["publish_checklist"])
        return publish_catalog(catalog)

    draft = (
        TaxRuleCatalog.objects.filter(
            tenant=tenant, status=TaxRuleCatalog.Status.DRAFT
        )
        .order_by("-version")
        .first()
    )
    if draft is None:
        draft = create_catalog(tenant=tenant)
    if not MunicipalTaxRule.objects.filter(catalog=draft, **rule_filter).exists():
        add_rule(
            catalog=draft,
            fiscal_profile=profile,
            ibge_code=ibge_digits,
            municipio_nome=municipio,
            uf=uf2,
            service_code=code,
            tax_regime=regime,
            iss_rate=rate,
            simples_codigo_tributacao=simples_codigo_tributacao,
            valid_from=v_from,
        )
    draft.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    draft.save(update_fields=["publish_checklist"])
    return publish_catalog(draft)
