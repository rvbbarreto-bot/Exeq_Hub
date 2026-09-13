from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.fiscal.exceptions import (
    CatalogNotEditableError,
    PublishChecklistIncompleteError,
    TaxRuleNotFoundError,
)
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog

CHECKLIST_KEYS = ("csv_validated", "rules_reviewed", "terms_accepted")


def assert_catalog_editable(catalog: TaxRuleCatalog) -> None:
    if catalog.status != TaxRuleCatalog.Status.DRAFT:
        raise CatalogNotEditableError("Catálogo publicado ou supersedido não pode ser editado")


def next_catalog_version(tenant) -> int:
    last = (
        TaxRuleCatalog.objects.filter(tenant=tenant)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return (last or 0) + 1


def create_catalog(*, tenant) -> TaxRuleCatalog:
    return TaxRuleCatalog.objects.create(
        tenant=tenant,
        version=next_catalog_version(tenant),
        status=TaxRuleCatalog.Status.DRAFT,
    )


def add_rule(*, catalog: TaxRuleCatalog, fiscal_profile: FiscalProfile, **fields) -> MunicipalTaxRule:
    assert_catalog_editable(catalog)
    return MunicipalTaxRule.objects.create(
        tenant=catalog.tenant,
        catalog=catalog,
        fiscal_profile=fiscal_profile,
        **fields,
    )


@transaction.atomic
def publish_catalog(catalog: TaxRuleCatalog) -> TaxRuleCatalog:
    assert_catalog_editable(catalog)
    checklist = catalog.publish_checklist or {}
    missing = [key for key in CHECKLIST_KEYS if not checklist.get(key)]
    if missing:
        raise PublishChecklistIncompleteError(missing)

    TaxRuleCatalog.objects.filter(
        tenant=catalog.tenant,
        status=TaxRuleCatalog.Status.PUBLISHED,
    ).update(status=TaxRuleCatalog.Status.SUPERSEDED)

    catalog.status = TaxRuleCatalog.Status.PUBLISHED
    catalog.published_at = timezone.now()
    catalog.save(update_fields=["status", "published_at", "updated_at"])
    return catalog


def _service_code_candidates(*, service_code: str, service=None) -> list[str]:
    """Códigos possíveis para casar regra municipal × serviço (LC ou nacional)."""
    out: list[str] = []

    def _add(value: str | None) -> None:
        text = (value or "").strip()
        if text and text not in out:
            out.append(text)

    _add(service_code)
    if service is not None:
        _add(getattr(service, "service_code", None))
        _add(getattr(service, "codigo_tributacao_nacional_iss", None))
        _add(getattr(service, "lc116_item", None))
        nacional = (getattr(service, "codigo_tributacao_nacional_iss", None) or "").strip()
        if nacional:
            from apps.master_data.national_service_import import (
                get_published_national_services,
            )

            _version, items = get_published_national_services()
            nat = None
            if _version is not None:
                nat = items.filter(codigo=nacional).first()
                if nat is None:
                    digits = "".join(ch for ch in nacional if ch.isdigit())
                    if digits:
                        nat = items.filter(codigo=digits).first()
            if nat is not None:
                _add(nat.lc116_hint)
                _add(nat.codigo)
                if nat.item and nat.subitem:
                    _add(f"{nat.item}.{nat.subitem:02d}")
                    _add(f"{nat.item}.{nat.subitem}")
    return out


def _base_rule_qs(
    *,
    tenant,
    catalog: TaxRuleCatalog,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    tax_regime: str,
    competence_date: date,
):
    return (
        MunicipalTaxRule.objects.filter(
            tenant=tenant,
            catalog=catalog,
            fiscal_profile=fiscal_profile,
            ibge_code=ibge_code,
            tax_regime=tax_regime,
            valid_from__lte=competence_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=competence_date))
        .order_by("priority", "-valid_from")
    )


def resolve_tax_rule(
    *,
    tenant,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    service_code: str,
    tax_regime: str,
    competence_date: date,
    service=None,
) -> MunicipalTaxRule:
    rule, _meta = resolve_tax_rule_detailed(
        tenant=tenant,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge_code,
        service_code=service_code,
        tax_regime=tax_regime,
        competence_date=competence_date,
        service=service,
    )
    return rule


def resolve_tax_rule_detailed(
    *,
    tenant,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    service_code: str,
    tax_regime: str,
    competence_date: date,
    service=None,
) -> tuple[MunicipalTaxRule, dict]:
    """
    Resolve regra municipal.
    1) match exato/alias (service_code, nacional, LC 116 / hint da lista nacional)
    2) se serviço pré-cadastrado na lista nacional e TAX_RULE_NATIONAL_FALLBACK,
       usa regra do mesmo perfil/IBGE/regime (ISS municipal)
    """
    catalog = TaxRuleCatalog.objects.filter(
        tenant=tenant,
        status=TaxRuleCatalog.Status.PUBLISHED,
    ).first()
    if catalog is None:
        raise TaxRuleNotFoundError("Nenhum catálogo published")

    base = _base_rule_qs(
        tenant=tenant,
        catalog=catalog,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge_code,
        tax_regime=tax_regime,
        competence_date=competence_date,
    )
    candidates = _service_code_candidates(service_code=service_code, service=service)
    for code in candidates:
        rule = base.filter(service_code=code).first()
        if rule is not None:
            mode = "exact" if code == (service_code or "").strip() else "alias"
            return rule, {
                "match_mode": mode,
                "requested_service_code": service_code,
                "matched_rule_service_code": rule.service_code,
                "candidate_codes": candidates,
            }

    allow_fallback = getattr(settings, "TAX_RULE_NATIONAL_FALLBACK", True)
    nacional = ""
    if service is not None:
        nacional = (getattr(service, "codigo_tributacao_nacional_iss", None) or "").strip()
    if not nacional:
        nacional = (service_code or "").strip()

    in_national = False
    if allow_fallback and nacional:
        from apps.master_data.national_service_import import get_published_national_services

        version, items = get_published_national_services()
        if version is not None:
            in_national = items.filter(codigo=nacional).exists()
            if not in_national:
                digits = "".join(ch for ch in nacional if ch.isdigit())
                in_national = bool(digits) and items.filter(codigo=digits).exists()

    if allow_fallback and in_national:
        rule = base.first()
        if rule is not None:
            return rule, {
                "match_mode": "national_fallback",
                "requested_service_code": service_code,
                "matched_rule_service_code": rule.service_code,
                "candidate_codes": candidates,
                "national_codigo": nacional,
            }

    raise TaxRuleNotFoundError("Regra tributária não encontrada")


def rule_to_payload(rule: MunicipalTaxRule, *, resolve_meta: dict | None = None) -> dict:
    from apps.fiscal.atibaia_ctribmun import resolve_c_trib_mun

    c_trib_mun = resolve_c_trib_mun(
        ibge_code=rule.ibge_code,
        service_code=rule.service_code,
        rule_c_trib_mun=getattr(rule, "c_trib_mun", "") or "",
    )
    payload = {
        "rule_id": str(rule.id),
        "ibge_code": rule.ibge_code,
        "service_code": rule.service_code,
        "tax_regime": rule.tax_regime,
        "iss_rate": str(rule.iss_rate),
        "irrf_rate": str(rule.irrf_rate),
        "pis_rate": str(rule.pis_rate),
        "cofins_rate": str(rule.cofins_rate),
        "iss_retained": rule.iss_retained,
        "simples_codigo_tributacao": rule.simples_codigo_tributacao,
        "priority": rule.priority,
    }
    if c_trib_mun:
        payload["c_trib_mun"] = c_trib_mun
    if resolve_meta:
        payload["resolve_meta"] = resolve_meta
    return payload
