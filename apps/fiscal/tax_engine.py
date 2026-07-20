from datetime import date
from decimal import Decimal

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


def resolve_tax_rule(
    *,
    tenant,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    service_code: str,
    tax_regime: str,
    competence_date: date,
) -> MunicipalTaxRule:
    catalog = TaxRuleCatalog.objects.filter(
        tenant=tenant,
        status=TaxRuleCatalog.Status.PUBLISHED,
    ).first()
    if catalog is None:
        raise TaxRuleNotFoundError("Nenhum catálogo published")

    rule = (
        MunicipalTaxRule.objects.filter(
            tenant=tenant,
            catalog=catalog,
            fiscal_profile=fiscal_profile,
            ibge_code=ibge_code,
            service_code=service_code,
            tax_regime=tax_regime,
            valid_from__lte=competence_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=competence_date))
        .order_by("priority", "-valid_from")
        .first()
    )
    if rule is None:
        raise TaxRuleNotFoundError("Regra tributária não encontrada")
    return rule


def rule_to_payload(rule: MunicipalTaxRule) -> dict:
    return {
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
