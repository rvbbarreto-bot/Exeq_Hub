"""Provisionamento idempotente da matriz fiscal EXEQ Lab (Sprint A)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from django.db import transaction

from apps.accounts.models import Tenant
from apps.fiscal.models import FiscalProfile
from apps.fiscal.templates_factory import apply_template
from apps.master_data.models import Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import create_service

EXEQ_LAB_CNPJ = "37229907000137"
EXEQ_LAB_IBGE = "3504107"

SERVICE_ROWS: tuple[dict[str, str], ...] = (
    {
        "service_code": "SVC-SUP-TI",
        "description": "Suporte técnico em TI",
        "lc116_item": "01.07",
        "codigo_tributacao_nacional_iss": "010701",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-DEV-ENC",
        "description": "Desenvolvimento de software sob encomenda",
        "lc116_item": "01.01",
        "codigo_tributacao_nacional_iss": "010101",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-SW-CUST",
        "description": "Licenciamento / software customizável",
        "lc116_item": "01.05",
        "codigo_tributacao_nacional_iss": "010501",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-SW-PAD",
        "description": "Licenciamento / SaaS padronizado",
        "lc116_item": "01.05",
        "codigo_tributacao_nacional_iss": "010501",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-CONS-TI",
        "description": "Consultoria em tecnologia da informação",
        "lc116_item": "01.06",
        "codigo_tributacao_nacional_iss": "010601",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-HOST-SaaS",
        "description": "Hospedagem, processamento e plataforma",
        "lc116_item": "01.03",
        "codigo_tributacao_nacional_iss": "010301",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-CORRET-IM",
        "description": "Corretagem e intermediação imobiliária",
        "lc116_item": "10.05",
        "codigo_tributacao_nacional_iss": "100501",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "SVC-ADM-IM",
        "description": "Administração de imóveis de terceiros",
        "lc116_item": "17.12",
        "codigo_tributacao_nacional_iss": "171201",
        "operation_kind": ServiceCatalogItem.OperationKind.SERVICO_ISS,
    },
    {
        "service_code": "OP-LOC-AUTO",
        "description": "Locação de automóvel sem condutor",
        "lc116_item": "",
        "codigo_tributacao_nacional_iss": "",
        "operation_kind": ServiceCatalogItem.OperationKind.LOCACAO_BEM,
    },
    {
        "service_code": "OP-LOC-OUT",
        "description": "Locação de outros veículos sem condutor",
        "lc116_item": "",
        "codigo_tributacao_nacional_iss": "",
        "operation_kind": ServiceCatalogItem.OperationKind.LOCACAO_BEM,
    },
)

EXEQ_LAB_CNAES_SECUNDARIOS = (
    "6201501",
    "6202300",
    "6203100",
    "6204000",
    "6311900",
    "6821801",
    "6822600",
    "7711000",
    "7719599",
)


@dataclass
class ProvisionResult:
    tenant_slug: str
    provider_cnpj: str
    fiscal_profile_name: str
    services_created: list[str] = field(default_factory=list)
    services_updated: list[str] = field(default_factory=list)
    template_applied: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


@transaction.atomic
def provision_exeq_lab_fiscal(
    *,
    tenant_slug: str = "exeq-lab",
    fiscal_profile_name: str = "SN-EXEQ-LAB",
    cnpj: str = EXEQ_LAB_CNPJ,
    template_id: str = "exeq-lab-sn-v1",
    apply_rules: bool = True,
) -> ProvisionResult:
    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        raise ValueError(f"Tenant não encontrado: {tenant_slug}")

    result = ProvisionResult(
        tenant_slug=tenant_slug,
        provider_cnpj=_digits(cnpj),
        fiscal_profile_name=fiscal_profile_name,
    )

    provider = Provider.objects.filter(tenant=tenant, document=result.provider_cnpj).first()
    if provider is not None:
        addr = dict(provider.address or {})
        addr.setdefault("codigo_ibge", EXEQ_LAB_IBGE)
        addr.setdefault("codigo_municipio_ibge", EXEQ_LAB_IBGE)
        addr.setdefault("municipio", "Atibaia")
        addr.setdefault("uf", "SP")
        addr.setdefault("municipio", "Atibaia")
        addr.setdefault("uf", "SP")
        provider.address = addr
        provider.cnae_principal = provider.cnae_principal or "6209100"
        provider.cnaes_secundarios = list(EXEQ_LAB_CNAES_SECUNDARIOS)
        provider.tax_regime = TaxRegime.SIMPLES
        provider.save(
            update_fields=[
                "address",
                "cnae_principal",
                "cnaes_secundarios",
                "tax_regime",
                "updated_at",
            ]
        )
    else:
        result.notes.append(
            f"Prestador CNPJ {result.provider_cnpj} não encontrado — serviços/regras only."
        )

    profile, created = FiscalProfile.objects.get_or_create(
        tenant=tenant,
        name=fiscal_profile_name,
        defaults={
            "tax_regime": TaxRegime.SIMPLES,
            "status": "active",
        },
    )
    if not created and profile.tax_regime != TaxRegime.SIMPLES:
        profile.tax_regime = TaxRegime.SIMPLES
        profile.status = "active"
        profile.save(update_fields=["tax_regime", "status", "updated_at"])

    for row in SERVICE_ROWS:
        code = row["service_code"]
        obj = ServiceCatalogItem.objects.filter(tenant=tenant, service_code=code).first()
        if obj is None:
            create_service(
                tenant=tenant,
                service_code=code,
                description=row["description"],
                lc116_item=row["lc116_item"],
                codigo_tributacao_nacional_iss=row["codigo_tributacao_nacional_iss"],
                operation_kind=row["operation_kind"],
                is_active=True,
            )
            result.services_created.append(code)
        else:
            changed = False
            for attr in (
                "description",
                "lc116_item",
                "codigo_tributacao_nacional_iss",
                "operation_kind",
            ):
                new_val = row[attr]
                if getattr(obj, attr) != new_val:
                    setattr(obj, attr, new_val)
                    changed = True
            if not obj.is_active:
                obj.is_active = True
                changed = True
            if changed:
                obj.save()
                result.services_updated.append(code)

    if apply_rules:
        tpl = apply_template(
            tenant=tenant,
            profile=profile,
            template_id=template_id,
        )
        result.template_applied = list(tpl.get("applied_service_codes") or [])

    return result
