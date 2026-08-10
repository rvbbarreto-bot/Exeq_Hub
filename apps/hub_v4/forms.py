"""Helpers de formulário Hub — prestador/tomador (fora do Admin)."""

from __future__ import annotations

import json
from typing import Any

from apps.accounts.plan_limits import PlanLimitError, assert_can_add_active_provider
from apps.master_data.models import Customer, DataSource, Provider, TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from shared.validators import validate_cnpj, validate_cpf


def addr_from_post(post) -> dict[str, str]:
    return {
        "logradouro": (post.get("logradouro") or "").strip(),
        "numero": (post.get("numero") or "").strip(),
        "complemento": (post.get("complemento") or "").strip(),
        "bairro": (post.get("bairro") or "").strip(),
        "cep": "".join(ch for ch in (post.get("cep") or "") if ch.isdigit())[:8],
        "municipio": (post.get("municipio") or "").strip(),
        "uf": (post.get("uf") or "").strip().upper()[:2],
        "codigo_municipio_ibge": (post.get("codigo_municipio_ibge") or "").strip(),
        "telefone": (post.get("telefone_receita") or post.get("telefone") or "").strip(),
        "email": (post.get("email_receita") or post.get("email_addr") or "").strip(),
    }


def cadastral_from_post(post) -> dict[str, Any]:
    data_abertura = (post.get("data_abertura") or "").strip() or None
    raw = post.get("receita_raw_payload") or ""
    payload = None
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"unparsed": raw[:2000]}
    source = (post.get("data_source") or DataSource.MANUAL).strip()
    if source not in {DataSource.MANUAL, DataSource.RECEITA}:
        source = DataSource.MANUAL
    out: dict[str, Any] = {
        "situacao_cadastral": (post.get("situacao_cadastral") or "").strip(),
        "data_abertura": data_abertura,
        "cnae_principal": (post.get("cnae_principal") or "").strip(),
        "natureza_juridica": (post.get("natureza_juridica") or "").strip(),
        "porte": (post.get("porte") or "").strip(),
        "whatsapp": (post.get("whatsapp") or "").strip(),
        "contato_nome": (post.get("contato_nome") or "").strip(),
        "data_source": source,
        "receita_raw_payload": payload,
        "address": addr_from_post(post),
    }
    if source == DataSource.RECEITA and payload:
        from django.utils import timezone

        out["last_lookup_at"] = timezone.now()
    return out


def save_provider_from_post(*, tenant, post, obj: Provider | None = None) -> Provider:
    document = validate_cnpj(post.get("document") or "")
    legal_name = (post.get("legal_name") or "").strip()
    if not legal_name:
        raise ValueError("Informe a razão social.")
    trade_name = (post.get("trade_name") or "").strip()
    tax_regime = (post.get("tax_regime") or TaxRegime.SIMPLES).strip()
    municipal = (post.get("municipal_registration") or "").strip()
    state_reg = (post.get("state_registration") or "").strip()
    is_active = (post.get("is_active") or "1") in {"1", "true", "on", "yes"}
    cadastral = cadastral_from_post(post)

    if obj is None:
        return create_provider(
            tenant=tenant,
            document=document,
            legal_name=legal_name,
            tax_regime=tax_regime,
            trade_name=trade_name,
            municipal_registration=municipal,
            state_registration=state_reg,
            is_active=is_active,
            **cadastral,
        )

    was_active = bool(obj.is_active)
    if is_active and not was_active:
        assert_can_add_active_provider(tenant)

    obj.document = document
    obj.legal_name = legal_name
    obj.trade_name = trade_name
    obj.tax_regime = tax_regime
    obj.municipal_registration = municipal
    obj.state_registration = state_reg
    obj.is_active = is_active
    for key, value in cadastral.items():
        setattr(obj, key, value)
    if cadastral.get("data_source") == DataSource.RECEITA and obj.last_lookup_at is None:
        from django.utils import timezone

        obj.last_lookup_at = timezone.now()
    obj.save()
    return obj


def save_customer_from_post(*, tenant, post, obj: Customer | None = None) -> Customer:
    document_type = (post.get("document_type") or Customer.DocumentType.CNPJ).strip()
    if document_type not in {Customer.DocumentType.CPF, Customer.DocumentType.CNPJ}:
        document_type = Customer.DocumentType.CNPJ
    raw_doc = post.get("document") or ""
    if document_type == Customer.DocumentType.CPF:
        document = validate_cpf(raw_doc)
    else:
        document = validate_cnpj(raw_doc)
    name = (post.get("name") or "").strip()
    if not name:
        raise ValueError("Informe o nome do tomador.")
    email = (post.get("email") or "").strip()
    is_active = (post.get("is_active") or "1") in {"1", "true", "on", "yes"}
    cadastral = cadastral_from_post(post)

    if obj is None:
        return create_customer(
            tenant=tenant,
            document=document,
            document_type=document_type,
            name=name,
            email=email,
            is_active=is_active,
            **cadastral,
        )

    obj.document = document
    obj.document_type = document_type
    obj.name = name
    obj.email = email
    obj.is_active = is_active
    for key, value in cadastral.items():
        setattr(obj, key, value)
    obj.save()
    return obj


def save_fiscal_profile_from_post(*, tenant, post, obj=None):
    from apps.fiscal.bootstrap import ensure_published_rule
    from apps.fiscal.models import FiscalProfile

    name = (post.get("name") or "").strip()
    if not name:
        raise ValueError("Informe o nome do perfil fiscal.")
    tax_regime = (post.get("tax_regime") or TaxRegime.SIMPLES).strip()
    retention = (post.get("iss_retention_policy") or "by_rule").strip() or "by_rule"
    status = (post.get("status") or "active").strip() or "active"

    if obj is None:
        if FiscalProfile.objects.filter(tenant=tenant, name=name).exists():
            raise ValueError("Já existe um perfil com este nome.")
        profile = FiscalProfile.objects.create(
            tenant=tenant,
            name=name,
            tax_regime=tax_regime,
            iss_retention_policy=retention,
            status=status,
        )
    else:
        if (
            FiscalProfile.objects.filter(tenant=tenant, name=name)
            .exclude(pk=obj.pk)
            .exists()
        ):
            raise ValueError("Já existe um perfil com este nome.")
        obj.name = name
        obj.tax_regime = tax_regime
        obj.iss_retention_policy = retention
        obj.status = status
        obj.save()
        profile = obj

    ensure = (post.get("ensure_rule") or "") in {"1", "true", "on", "yes"}
    if ensure:
        from decimal import Decimal

        raw_rate = (post.get("iss_rate") or "0.02").strip().replace(",", ".")
        try:
            rate = Decimal(raw_rate)
        except Exception as exc:
            raise ValueError("Alíquota ISS inválida.") from exc
        ensure_published_rule(
            tenant=tenant,
            profile=profile,
            ibge=post.get("ibge_code") or "",
            municipio_nome=(post.get("municipio_nome") or "").strip(),
            uf=(post.get("uf") or "").strip(),
            service_code=(post.get("rule_service_code") or "").strip(),
            tax_regime=profile.tax_regime,
            iss_rate=rate,
            simples_codigo_tributacao=3 if profile.tax_regime == TaxRegime.SIMPLES else None,
        )
    return profile


def save_tax_rule_from_post(*, tenant, post):
    """Publica (ou reaproveita) regra profile × IBGE × serviço no catálogo published."""
    from decimal import Decimal

    from apps.fiscal.bootstrap import ensure_published_rule
    from apps.fiscal.models import FiscalProfile

    profile_id = (post.get("fiscal_profile_id") or "").strip()
    profile = FiscalProfile.objects.filter(tenant=tenant, pk=profile_id).first()
    if profile is None:
        raise ValueError("Selecione um perfil fiscal válido.")
    raw_rate = (post.get("iss_rate") or "0.02").strip().replace(",", ".")
    try:
        rate = Decimal(raw_rate)
    except Exception as exc:
        raise ValueError("Alíquota ISS inválida.") from exc
    return ensure_published_rule(
        tenant=tenant,
        profile=profile,
        ibge=post.get("ibge_code") or "",
        municipio_nome=(post.get("municipio_nome") or "").strip(),
        uf=(post.get("uf") or "").strip(),
        service_code=(post.get("service_code") or "").strip(),
        tax_regime=profile.tax_regime,
        iss_rate=rate,
        simples_codigo_tributacao=3 if profile.tax_regime == TaxRegime.SIMPLES else None,
    )


def save_service_from_post(*, tenant, post, obj=None):
    from apps.master_data.models import ServiceCatalogItem

    code = (post.get("service_code") or "").strip()
    description = (post.get("description") or "").strip()
    if not code:
        raise ValueError("Informe o código do serviço.")
    if not description:
        raise ValueError("Informe a descrição do serviço.")
    lc116 = (post.get("lc116_item") or "").strip()
    nacional = (post.get("codigo_tributacao_nacional_iss") or "").strip()
    is_active = (post.get("is_active") or "1") in {"1", "true", "on", "yes"}

    if obj is None:
        if ServiceCatalogItem.objects.filter(tenant=tenant, service_code=code).exists():
            raise ValueError("Já existe serviço com este código.")
        return create_service(
            tenant=tenant,
            service_code=code,
            description=description,
            lc116_item=lc116,
            codigo_tributacao_nacional_iss=nacional,
            is_active=is_active,
        )

    if (
        ServiceCatalogItem.objects.filter(tenant=tenant, service_code=code)
        .exclude(pk=obj.pk)
        .exists()
    ):
        raise ValueError("Já existe serviço com este código.")
    obj.service_code = code
    obj.description = description
    obj.lc116_item = lc116
    obj.codigo_tributacao_nacional_iss = nacional
    obj.is_active = is_active
    obj.save()
    return obj


def _parse_brl_to_cents(raw: str) -> int:
    from decimal import Decimal, InvalidOperation

    text = (raw or "0").strip()
    if not text:
        return 0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Preço unitário inválido") from exc
    cents = int((amount * 100).quantize(Decimal("1")))
    if cents < 0:
        raise ValueError("Preço unitário não pode ser negativo")
    return cents


def _parse_percent_to_bp(raw: str) -> int:
    """Ex.: '18' ou '18,00' → 1800 basis points."""
    from decimal import Decimal, InvalidOperation

    text = (raw or "0").strip()
    if not text:
        return 0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        pct = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Alíquota inválida") from exc
    return max(0, int((pct * 100).quantize(Decimal("1"))))


def save_nfe_product_from_post(*, tenant, post, obj=None):
    """CRUD catálogo SKU fiscal NF-e (Hub)."""
    from apps.nfe.exceptions import NfeDisabledError, NfeValidationError
    from apps.nfe.services import create_product, update_product

    code = (post.get("code") or "").strip()
    description = (post.get("description") or "").strip()
    ncm = (post.get("ncm") or "").strip()
    unit = (post.get("unit") or "UN").strip() or "UN"
    origin = (post.get("origin") or "0").strip() or "0"
    cfop_int = (post.get("cfop_internal") or "5102").strip() or "5102"
    cfop_inter = (post.get("cfop_interstate") or "6102").strip() or "6102"
    csosn = (post.get("csosn") or "").strip()
    icms_cst = (post.get("icms_cst") or "").strip()
    pis_cst = (post.get("pis_cst") or "07").strip() or "07"
    cofins_cst = (post.get("cofins_cst") or "07").strip() or "07"
    is_active = (post.get("is_active") or "1") in {"1", "true", "on", "yes"}
    unit_cents = _parse_brl_to_cents(post.get("unit_price") or "0")
    icms_bp = _parse_percent_to_bp(post.get("icms_rate") or "0")
    pis_bp = _parse_percent_to_bp(post.get("pis_rate") or "0")
    cofins_bp = _parse_percent_to_bp(post.get("cofins_rate") or "0")

    try:
        if obj is None:
            return create_product(
                tenant=tenant,
                code=code,
                description=description,
                ncm=ncm,
                unit_price_cents=unit_cents,
                unit=unit,
                origin=origin,
                cfop_internal=cfop_int,
                cfop_interstate=cfop_inter,
                csosn=csosn or "102",
                icms_cst=icms_cst,
                icms_rate_bp=icms_bp,
                pis_cst=pis_cst,
                pis_rate_bp=pis_bp,
                cofins_cst=cofins_cst,
                cofins_rate_bp=cofins_bp,
                is_active=is_active,
            )
        return update_product(
            obj,
            code=code,
            description=description,
            ncm=ncm,
            unit_price_cents=unit_cents,
            unit=unit,
            origin=origin,
            cfop_internal=cfop_int,
            cfop_interstate=cfop_inter,
            csosn=csosn,
            icms_cst=icms_cst,
            icms_rate_bp=icms_bp,
            pis_cst=pis_cst,
            pis_rate_bp=pis_bp,
            cofins_cst=cofins_cst,
            cofins_rate_bp=cofins_bp,
            is_active=is_active,
        )
    except (NfeDisabledError, NfeValidationError) as exc:
        raise ValueError(str(exc)) from exc


def provider_form_error_message(exc: Exception) -> str:
    if isinstance(exc, PlanLimitError):
        return str(exc)
    return str(exc) or "Não foi possível salvar."
