import pytest

from apps.master_data.models import ServiceCatalogItem
from apps.master_data.service_validation import normalize_ctn_iss
from apps.master_data.services import create_service


@pytest.mark.django_db
def test_create_service_rejects_invalid_ctn(tenant_a):
    with pytest.raises(ValueError, match="6 dígitos"):
        create_service(
            tenant=tenant_a,
            service_code="BAD-CTN",
            description="Teste",
            codigo_tributacao_nacional_iss="101",
        )


@pytest.mark.django_db
def test_create_service_normalizes_ctn(tenant_a):
    svc = create_service(
        tenant=tenant_a,
        service_code="OK-CTN",
        description="Teste",
        codigo_tributacao_nacional_iss="010701",
    )
    assert svc.codigo_tributacao_nacional_iss == "010701"


@pytest.mark.django_db
def test_create_service_locacao_clears_fiscal_codes(tenant_a):
    svc = create_service(
        tenant=tenant_a,
        service_code="LOC-1",
        description="Locação",
        operation_kind=ServiceCatalogItem.OperationKind.LOCACAO_BEM,
        lc116_item="77.11",
        codigo_tributacao_nacional_iss="771100",
    )
    assert svc.lc116_item == ""
    assert svc.codigo_tributacao_nacional_iss == ""


def test_normalize_ctn_strips_non_digits():
    assert normalize_ctn_iss("01.07.01") == "010701"
