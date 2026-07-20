from apps.master_data.models import Customer, Provider, ServiceCatalogItem
from shared.validators import validate_cnpj, validate_cpf


def create_provider(*, tenant, document: str, legal_name: str, tax_regime: str, **extra) -> Provider:
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


def create_service(*, tenant, service_code: str, description: str, **extra) -> ServiceCatalogItem:
    return ServiceCatalogItem.objects.create(
        tenant=tenant,
        service_code=service_code,
        description=description,
        **extra,
    )
