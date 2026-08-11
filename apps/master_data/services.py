from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.master_data.models import Customer, DataSource, Provider
from integrations.cadastro.exceptions import (
    CadastroCpfLookupNotSupportedError,
    CadastroDocumentInvalidError,
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)
from integrations.cadastro.factory import get_cadastro_gateway, get_cep_gateway
from integrations.cadastro.mappers import map_brasilapi_cnpj
from integrations.cadastro.port import CadastralLookupResult
from shared.validators import validate_cnpj, validate_cpf


def create_provider(*, tenant, document: str, legal_name: str, tax_regime: str, **extra) -> Provider:
    from apps.accounts.plan_limits import assert_can_add_active_provider

    is_active = extra.get("is_active", True)
    if is_active:
        assert_can_add_active_provider(tenant)
    return Provider.objects.create(
        tenant=tenant,
        document=validate_cnpj(document),
        legal_name=legal_name,
        tax_regime=tax_regime,
        **extra,
    )


def create_customer(
    *,
    tenant,
    document: str,
    document_type: str,
    name: str,
    **extra,
) -> Customer:
    if document_type == Customer.DocumentType.CPF:
        digits = validate_cpf(document)
    else:
        digits = validate_cnpj(document)
    return Customer.objects.create(
        tenant=tenant,
        document=digits,
        document_type=document_type,
        name=name,
        **extra,
    )


def create_service(*, tenant, service_code: str, description: str, **extra):
    from apps.master_data.models import ServiceCatalogItem

    return ServiceCatalogItem.objects.create(
        tenant=tenant,
        service_code=service_code,
        description=description,
        **extra,
    )


# Catálogo mínimo quando o tenant ainda não tem serviços (lab / onboarding).
# Após import+materialize da Lista Nacional, estes não são recriados.
_SEED_SERVICES: tuple[tuple[str, str, str], ...] = (
    (
        "01.07",
        "01.07",
        "Suporte técnico em informática, inclusive instalação, configuração e "
        "manutenção de programas de computação e bancos de dados.",
    ),
    (
        "17.01",
        "17.01",
        "Assessoria ou consultoria de qualquer natureza; análise, pesquisa e "
        "fornecimento de dados e informações de qualquer natureza.",
    ),
    (
        "17.19",
        "17.19",
        "Contabilidade, inclusive serviços técnicos e auxiliares.",
    ),
    (
        "14.01",
        "14.01",
        "Lubrificação, limpeza, lustração, revisão, carga e recarga, conserto, "
        "restauração, blindagem, manutenção e conservação de máquinas, veículos, "
        "aparelhos, equipamentos, motores, elevadores ou de qualquer objeto.",
    ),
)


def ensure_services_for_wizard(*, tenant, limit: int = 500) -> list:
    """
    Garante opções no select Serviço do wizard NFS-e.
    1) Catálogo do tenant (ativos)
    2) Materializa Lista Nacional publicada, se existir
    3) Semeia itens mínimos de LC 116 para operação inicial
    """
    from apps.master_data.models import ServiceCatalogItem

    def active():
        return ServiceCatalogItem.objects.filter(tenant=tenant, is_active=True).order_by(
            "service_code"
        )

    qs = active()
    if qs.exists():
        return list(qs[:limit])

    try:
        from apps.master_data.national_service_import import (
            NationalServiceImportError,
            materialize_national_services_for_tenant,
        )

        materialize_national_services_for_tenant(tenant=tenant, only_missing=True)
    except NationalServiceImportError:
        pass

    qs = active()
    if qs.exists():
        return list(qs[:limit])

    for code, lc116, description in _SEED_SERVICES:
        ServiceCatalogItem.objects.get_or_create(
            tenant=tenant,
            service_code=code,
            defaults={
                "description": description,
                "lc116_item": lc116,
                "is_active": True,
            },
        )
    return list(active()[:limit])


def _cache_ttl() -> timedelta:
    hours = int(getattr(settings, "CADASTRO_LOOKUP_CACHE_HOURS", 24) or 24)
    return timedelta(hours=hours)


def _result_from_cached_entity(entity: Provider | Customer) -> CadastralLookupResult | None:
    raw = entity.receita_raw_payload
    if not isinstance(raw, dict) or not entity.last_lookup_at:
        return None
    if timezone.now() - entity.last_lookup_at > _cache_ttl():
        return None
    # Não reutilizar cache inventado pelo stub quando o modo atual é HTTP (Receita real).
    mode = (getattr(settings, "CADASTRO_HTTP_MODE", None) or "stub").lower()
    if mode == "http" and (
        raw.get("mode") == "stub"
        or str(raw.get("provider") or "").endswith("stub")
        or str(raw.get("provider") or "") == "cadastro_stub"
    ):
        return None
    document = entity.document
    raw_doc = "".join(ch for ch in str(raw.get("cnpj") or "") if ch.isdigit())
    if raw_doc and raw_doc != document:
        return None
    try:
        result = map_brasilapi_cnpj(
            raw,
            cnpj=document,
            provider_kind=str(raw.get("provider") or "cache"),
        )
    except Exception:
        # Payload stub/legado: monta a partir dos campos persistidos.
        from integrations.cadastro.port import CadastralAddress

        addr = entity.address if isinstance(entity.address, dict) else {}
        legal = (
            entity.legal_name
            if isinstance(entity, Provider)
            else entity.name
        )
        trade = entity.trade_name if isinstance(entity, Provider) else ""
        result = CadastralLookupResult(
            document=document,
            legal_name=legal,
            trade_name=trade,
            situacao_cadastral=entity.situacao_cadastral,
            data_abertura=entity.data_abertura,
            natureza_juridica=entity.natureza_juridica,
            cnae_principal=entity.cnae_principal,
            porte=entity.porte,
            address=CadastralAddress(
                logradouro=str(addr.get("logradouro") or ""),
                numero=str(addr.get("numero") or ""),
                complemento=str(addr.get("complemento") or ""),
                bairro=str(addr.get("bairro") or ""),
                cep=str(addr.get("cep") or ""),
                municipio=str(addr.get("municipio") or ""),
                uf=str(addr.get("uf") or ""),
                codigo_municipio_ibge=str(addr.get("codigo_municipio_ibge") or ""),
            ),
            telefone=str(addr.get("telefone") or ""),
            email=getattr(entity, "email", "") or str(addr.get("email") or ""),
            raw=raw,
            provider_kind="cache",
        )
    if result.document != document:
        return None
    return CadastralLookupResult(
        document=result.document,
        legal_name=result.legal_name,
        trade_name=result.trade_name,
        situacao_cadastral=result.situacao_cadastral,
        data_abertura=result.data_abertura,
        natureza_juridica=result.natureza_juridica,
        cnae_principal=result.cnae_principal,
        cnaes_secundarios=result.cnaes_secundarios,
        porte=result.porte,
        optante_simples=result.optante_simples,
        optante_mei=result.optante_mei,
        telefone=result.telefone,
        email=result.email,
        address=result.address,
        raw=result.raw,
        cached=True,
        provider_kind=result.provider_kind,
    )


def _find_cached(
    *,
    tenant,
    document: str,
    entity_kind: str,
) -> CadastralLookupResult | None:
    if entity_kind == "provider":
        entity = Provider.objects.filter(tenant=tenant, document=document).first()
    else:
        entity = Customer.objects.filter(
            tenant=tenant, document=document, document_type=Customer.DocumentType.CNPJ
        ).first()
    if entity is None:
        return None
    return _result_from_cached_entity(entity)


def apply_lookup_to_entity(
    entity: Provider | Customer,
    result: CadastralLookupResult,
) -> Provider | Customer:
    """Persiste enriquecimento cadastral em entidade já existente (reconsulta)."""
    now = timezone.now()
    address = dict(entity.address or {})
    address.update(result.address.as_dict())
    if result.telefone:
        address["telefone"] = result.telefone
    if result.email:
        address["email"] = result.email

    entity.situacao_cadastral = result.situacao_cadastral
    entity.data_abertura = result.data_abertura
    entity.cnae_principal = result.cnae_principal
    entity.natureza_juridica = result.natureza_juridica
    entity.porte = result.porte
    entity.address = address
    entity.data_source = DataSource.RECEITA
    entity.receita_raw_payload = result.raw
    entity.last_lookup_at = now

    if isinstance(entity, Provider):
        entity.legal_name = result.legal_name or entity.legal_name
        entity.trade_name = result.trade_name or entity.trade_name
    else:
        entity.name = result.legal_name or entity.name
        if result.email:
            entity.email = result.email

    entity.save()
    return entity


def lookup_document(
    *,
    tenant,
    document: str,
    entity_kind: str,
    force: bool = False,
    persist_on_existing: bool = False,
) -> CadastralLookupResult:
    """
    Consulta CNPJ sem criar registro.
    Se já existir Provider/Customer do tenant com cache < 24h, reutiliza.
    CPF: rejeitado (LGPD — sem bureau).
    """
    digits = "".join(ch for ch in (document or "") if ch.isdigit())
    if len(digits) == 11:
        try:
            validate_cpf(digits)
        except ValueError as exc:
            raise CadastroDocumentInvalidError(str(exc)) from exc
        raise CadastroCpfLookupNotSupportedError(
            "Consulta cadastral por CPF não está disponível (LGPD). "
            "Preencha nome e endereço manualmente."
        )

    try:
        digits = validate_cnpj(digits)
    except ValueError as exc:
        raise CadastroDocumentInvalidError(str(exc)) from exc

    if not force:
        cached = _find_cached(tenant=tenant, document=digits, entity_kind=entity_kind)
        if cached is not None:
            return cached

    try:
        gateway = get_cadastro_gateway()
        result = gateway.lookup_cnpj(cnpj=digits)
    except (CadastroNotFoundError, CadastroProviderUnavailableError):
        raise
    except Exception as exc:  # pragma: no cover — rede/desconhecido
        raise CadastroProviderUnavailableError(
            "Provedor cadastral indisponível. Preencha os dados manualmente."
        ) from exc

    if result.document != digits:
        raise CadastroProviderUnavailableError(
            "Resposta cadastral não corresponde ao CNPJ consultado. Tente novamente."
        )

    if persist_on_existing:
        if entity_kind == "provider":
            entity = Provider.objects.filter(tenant=tenant, document=digits).first()
        else:
            entity = Customer.objects.filter(
                tenant=tenant,
                document=digits,
                document_type=Customer.DocumentType.CNPJ,
            ).first()
        if entity is not None:
            apply_lookup_to_entity(entity, result)

    return result


def cadastral_fields_from_result(result: CadastralLookupResult) -> dict[str, Any]:
    """Campos prontos para create/update a partir da consulta (sem gravar ainda)."""
    address = result.address.as_dict()
    if result.telefone:
        address["telefone"] = result.telefone
    if result.email:
        address["email"] = result.email
    return {
        "situacao_cadastral": result.situacao_cadastral,
        "data_abertura": result.data_abertura,
        "cnae_principal": result.cnae_principal,
        "natureza_juridica": result.natureza_juridica,
        "porte": result.porte,
        "address": address,
        "data_source": DataSource.RECEITA,
        "receita_raw_payload": result.raw,
        "last_lookup_at": timezone.now(),
    }


def lookup_cep(*, cep: str):
    digits = "".join(ch for ch in (cep or "") if ch.isdigit())[:8]
    if len(digits) != 8:
        raise CadastroDocumentInvalidError("CEP inválido. Informe 8 dígitos.")
    try:
        return get_cep_gateway().lookup_cep(cep=digits)
    except (CadastroNotFoundError, CadastroProviderUnavailableError):
        raise
    except Exception as exc:  # pragma: no cover
        raise CadastroProviderUnavailableError(
            "Consulta de CEP indisponível. Preencha o endereço manualmente."
        ) from exc
