"""Onboarding idempotente multi-CNPJ / multi-tenant para NFS-e Nacional.

Garante tenant + membership + prestador + serviço + perfil/regra fiscal (+ A1 opcional)
sem novas tabelas — reutiliza services existentes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.certificates import assert_certificate_usable, upload_a1_certificate
from apps.accounts.membership_services import ensure_membership
from apps.accounts.models import DigitalCertificate, Tenant, TenantRole
from apps.accounts.services import ensure_system_roles
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.master_data.models import Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import create_provider, create_service

User = get_user_model()


@dataclass
class OnboardResult:
    tenant_id: str
    tenant_slug: str
    provider_id: str
    provider_cnpj: str
    service_id: str
    fiscal_profile_id: str
    catalog_id: str | None
    certificate_id: str | None
    user_email: str
    created: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _parse_tax_regime(value: str) -> str:
    raw = (value or TaxRegime.SIMPLES).strip().lower()
    aliases = {
        "sn": TaxRegime.SIMPLES,
        "simples": TaxRegime.SIMPLES,
        "simples_nacional": TaxRegime.SIMPLES,
    }
    if raw in aliases:
        return aliases[raw]
    if raw in {c.value for c in TaxRegime}:
        return raw
    raise ValueError(f"tax_regime inválido: {value}")


@transaction.atomic
def onboard_nfse_tenant(
    *,
    slug: str,
    cnpj: str,
    legal_name: str,
    user_email: str,
    user_password: str = "",
    role_code: str = "tenant_admin",
    tax_regime: str = TaxRegime.SIMPLES,
    municipal_registration: str = "",
    ibge_code: str = "3504107",
    municipio_nome: str = "Atibaia",
    uf: str = "SP",
    service_code: str = "170101",
    service_description: str = "Servico onboarding Hub SEFIN",
    c_trib_nac: str = "",
    fiscal_profile_name: str = "SN-ONBOARD",
    iss_rate: Decimal = Decimal("0.0200"),
    simples_codigo_tributacao: int = 3,
    valid_from: date | None = None,
    pfx_bytes: bytes | None = None,
    pfx_password: str = "",
    cert_label: str = "A1-onboard",
    skip_cert: bool = False,
) -> OnboardResult:
    """Idempotente: reexecutar não duplica tenant/provider/regra."""
    ensure_system_roles()
    created: dict[str, bool] = {}
    notes: list[str] = []

    slug = (slug or "").strip()
    digits = _digits(cnpj)
    if len(digits) != 14:
        raise ValueError("CNPJ do prestador deve ter 14 dígitos")
    if not slug:
        raise ValueError("slug obrigatório")
    email = (user_email or "").strip().lower()
    if not email:
        raise ValueError("user_email obrigatório")

    regime = _parse_tax_regime(tax_regime)
    ibge = _digits(ibge_code).zfill(7)
    svc_code = (service_code or "").strip()
    nacional = _digits(c_trib_nac) or _digits(svc_code)
    valid_from = valid_from or date(2024, 1, 1)

    tenant = Tenant.objects.filter(slug=slug).first()
    if tenant is None:
        # document único global — se CNPJ já for de outro tenant, falhar claro
        other = Tenant.objects.filter(document=digits).exclude(slug=slug).first()
        if other is not None:
            raise ValueError(
                f"CNPJ {digits} já vinculado ao tenant slug={other.slug}"
            )
        tenant = Tenant.objects.create(
            slug=slug,
            legal_name=legal_name,
            document=digits,
            status=Tenant.Status.ACTIVE,
            focus_layout="nfsen",
            settings={},
        )
        created["tenant"] = True
    else:
        created["tenant"] = False
        if _digits(tenant.document) != digits:
            raise ValueError(
                f"Tenant {slug} existe com document={tenant.document}; "
                f"esperado {digits}"
            )
        if legal_name and tenant.legal_name != legal_name:
            tenant.legal_name = legal_name
            tenant.save(update_fields=["legal_name", "updated_at"])
            notes.append("tenant.legal_name atualizado")

    role = TenantRole.objects.filter(code=role_code).first()
    if role is None:
        raise ValueError(f"role inexistente: {role_code}")

    user = User.objects.filter(email=email).first()
    if user is None:
        if not user_password:
            raise ValueError("user_password obrigatório para criar usuário")
        user = User.objects.create_user(
            email=email, password=user_password, name=legal_name[:120] or email
        )
        created["user"] = True
    else:
        created["user"] = False
        if user_password:
            user.set_password(user_password)
            user.save(update_fields=["password"])
            notes.append("user.password atualizado")

    membership, mem_created = ensure_membership(
        tenant=tenant,
        user=user,
        role=role,
        is_active=True,
    )
    created["membership"] = mem_created
    if not mem_created and membership.role_id != role.id:
        notes.append("membership.role atualizado")

    provider = Provider.objects.filter(tenant=tenant, document=digits).first()
    if provider is None:
        provider = create_provider(
            tenant=tenant,
            document=digits,
            legal_name=legal_name,
            tax_regime=regime,
            municipal_registration=municipal_registration or "",
        )
        created["provider"] = True
    else:
        created["provider"] = False
        dirty: list[str] = []
        if provider.legal_name != legal_name:
            provider.legal_name = legal_name
            dirty.append("legal_name")
        if provider.tax_regime != regime:
            provider.tax_regime = regime
            dirty.append("tax_regime")
        if municipal_registration and provider.municipal_registration != municipal_registration:
            provider.municipal_registration = municipal_registration
            dirty.append("municipal_registration")
        if dirty:
            provider.save(update_fields=[*dirty, "updated_at"])
            notes.append(f"provider atualizado: {', '.join(dirty)}")

    service = ServiceCatalogItem.objects.filter(
        tenant=tenant, service_code=svc_code
    ).first()
    if service is None:
        service = create_service(
            tenant=tenant,
            service_code=svc_code,
            description=service_description,
            codigo_tributacao_nacional_iss=nacional,
            lc116_item=(
                f"{nacional[:2]}.{nacional[2:4]}" if len(nacional) >= 4 else ""
            ),
        )
        created["service"] = True
    else:
        created["service"] = False
        if not service.codigo_tributacao_nacional_iss and nacional:
            service.codigo_tributacao_nacional_iss = nacional
            service.save(
                update_fields=["codigo_tributacao_nacional_iss", "updated_at"]
            )
            notes.append("service.cTribNac preenchido")

    profile = FiscalProfile.objects.filter(
        tenant=tenant, name=fiscal_profile_name
    ).first()
    if profile is None:
        profile = FiscalProfile.objects.create(
            tenant=tenant,
            name=fiscal_profile_name,
            tax_regime=regime,
        )
        created["fiscal_profile"] = True
    else:
        created["fiscal_profile"] = False
        if profile.tax_regime != regime:
            profile.tax_regime = regime
            profile.save(update_fields=["tax_regime", "updated_at"])

    catalog = _ensure_published_rule(
        tenant=tenant,
        profile=profile,
        ibge=ibge,
        municipio_nome=municipio_nome,
        uf=uf,
        service_code=svc_code,
        tax_regime=regime,
        iss_rate=iss_rate,
        simples_codigo_tributacao=simples_codigo_tributacao,
        valid_from=valid_from,
        created=created,
        notes=notes,
    )

    certificate_id: str | None = None
    if skip_cert:
        notes.append("certificado ignorado (--skip-cert)")
        created["certificate"] = False
    elif pfx_bytes:
        existing = (
            DigitalCertificate.objects.filter(
                tenant=tenant, cnpj=digits, is_primary=True
            )
            .order_by("-version")
            .first()
        )
        if existing is not None:
            try:
                assert_certificate_usable(
                    tenant=tenant, cnpj=digits, purpose="nfse"
                )
                certificate_id = str(existing.id)
                created["certificate"] = False
                if existing.provider_id is None:
                    existing.provider = provider
                    existing.save(update_fields=["provider", "updated_at"])
                    notes.append("cert.provider vinculado")
            except Exception:  # noqa: BLE001 — reupload se inutilizável
                certificate_id = None
                existing = None
        if certificate_id is None:
            cert = upload_a1_certificate(
                tenant=tenant,
                label=cert_label,
                cnpj=digits,
                pfx_bytes=pfx_bytes,
                password=pfx_password,
                provider=provider,
                key_usage=["das", "nfse"],
                make_primary=True,
            )
            certificate_id = str(cert.id)
            created["certificate"] = True
    else:
        primary = DigitalCertificate.objects.filter(
            tenant=tenant, cnpj=digits, is_primary=True
        ).first()
        if primary is not None:
            certificate_id = str(primary.id)
            notes.append("certificado primário já existente (sem --pfx)")
        else:
            notes.append("sem certificado — use --pfx para emissão SEFIN http")
        created["certificate"] = False

    return OnboardResult(
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        provider_id=str(provider.id),
        provider_cnpj=digits,
        service_id=str(service.id),
        fiscal_profile_id=str(profile.id),
        catalog_id=str(catalog.id) if catalog else None,
        certificate_id=certificate_id,
        user_email=email,
        created=created,
        notes=notes,
    )


def _ensure_published_rule(
    *,
    tenant,
    profile: FiscalProfile,
    ibge: str,
    municipio_nome: str,
    uf: str,
    service_code: str,
    tax_regime: str,
    iss_rate: Decimal,
    simples_codigo_tributacao: int,
    valid_from: date,
    created: dict[str, bool],
    notes: list[str],
) -> TaxRuleCatalog:
    from apps.fiscal.bootstrap import ensure_published_rule

    before = TaxRuleCatalog.objects.filter(
        tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
    ).first()
    had_rule = False
    if before is not None:
        had_rule = MunicipalTaxRule.objects.filter(
            tenant=tenant,
            catalog=before,
            fiscal_profile=profile,
            ibge_code="".join(ch for ch in ibge if ch.isdigit())[:7],
            service_code=service_code,
            tax_regime=tax_regime,
        ).exists()
    catalog = ensure_published_rule(
        tenant=tenant,
        profile=profile,
        ibge=ibge,
        municipio_nome=municipio_nome,
        uf=uf,
        service_code=service_code,
        tax_regime=tax_regime,
        iss_rate=iss_rate,
        simples_codigo_tributacao=simples_codigo_tributacao,
        valid_from=valid_from,
    )
    if had_rule:
        created["tax_rule"] = False
        created["catalog"] = False
    else:
        created["tax_rule"] = True
        created["catalog"] = before is None or catalog.id != before.id
        if before is not None and catalog.id != before.id:
            notes.append("novo catálogo publicado com regra IBGE/serviço (cópia + delta)")
        else:
            notes.append("regra municipal publicada para IBGE/serviço")
    return catalog
