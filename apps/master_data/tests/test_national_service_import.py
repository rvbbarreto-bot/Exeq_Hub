from pathlib import Path

import openpyxl
import pytest
from django.urls import reverse

from apps.master_data.models import (
    NationalServiceCatalogVersion,
    NationalServiceItem,
    ServiceCatalogItem,
)
from apps.master_data.national_service_import import (
    NationalServiceImportError,
    import_national_service_xlsx,
    materialize_national_services_for_tenant,
    publish_national_service_version,
)


def _write_sample_xlsx(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LISTA.SERV.NAC."
    ws.append(
        [
            "CÓDIGO DE TRIBUTAÇÃO NACIONAL",
            "ITEM",
            "SUBITEM",
            "DESDOBRO NACIONAL",
            "DESCRIÇÃO",
        ]
    )
    ws.append([None, 1, 0, 0, "Grupo informática"])
    ws.append([10101, 1, 1, 1, "Análise e desenvolvimento de sistemas."])
    ws.append([10201, 1, 2, 1, "Programação."])
    wb.create_sheet("LISTA.NBS_v2.0")
    wb["LISTA.NBS_v2.0"].append(["CÓDIGO NBS", "DESCRIÇÃO"])
    wb.save(path)


@pytest.mark.django_db
def test_import_national_service_xlsx_publishes(tmp_path):
    xlsx = tmp_path / "anexo_b.xlsx"
    _write_sample_xlsx(xlsx)
    version = import_national_service_xlsx(
        path=xlsx, version_label="2026-01-22-test", publish=True
    )
    assert version.status == NationalServiceCatalogVersion.Status.PUBLISHED
    assert version.row_count == 2
    codes = set(
        NationalServiceItem.objects.filter(version=version).values_list(
            "codigo", flat=True
        )
    )
    assert codes == {"10101", "10201"}
    item = NationalServiceItem.objects.get(version=version, codigo="10101")
    assert item.lc116_hint == "1.01"


@pytest.mark.django_db
def test_import_duplicate_version_label(tmp_path):
    xlsx = tmp_path / "anexo_b.xlsx"
    _write_sample_xlsx(xlsx)
    import_national_service_xlsx(path=xlsx, version_label="v1", publish=True)
    with pytest.raises(NationalServiceImportError):
        import_national_service_xlsx(path=xlsx, version_label="v1", publish=False)


@pytest.mark.django_db
def test_publish_supersedes_previous(tmp_path):
    xlsx = tmp_path / "anexo_b.xlsx"
    _write_sample_xlsx(xlsx)
    v1 = import_national_service_xlsx(path=xlsx, version_label="v-old", publish=True)
    xlsx2 = tmp_path / "anexo_b2.xlsx"
    _write_sample_xlsx(xlsx2)
    v2 = import_national_service_xlsx(path=xlsx2, version_label="v-new", publish=True)
    v1.refresh_from_db()
    assert v1.status == NationalServiceCatalogVersion.Status.SUPERSEDED
    assert v2.status == NationalServiceCatalogVersion.Status.PUBLISHED


@pytest.mark.django_db
def test_admin_import_get(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        email="admin@import.local", password="Secret123!", name="Admin"
    )
    client.force_login(user)
    url = reverse("admin:master_data_servicecatalogitem_import_anexo_b")
    res = client.get(url)
    assert res.status_code == 200
    assert b"Anexo B" in res.content


@pytest.mark.django_db
def test_materialize_national_services_for_tenant(tmp_path, tenant_a):
    xlsx = tmp_path / "anexo_b.xlsx"
    _write_sample_xlsx(xlsx)
    import_national_service_xlsx(path=xlsx, version_label="mat-v1", publish=True)

    result = materialize_national_services_for_tenant(tenant=tenant_a)
    assert result["created"] == 2
    assert result["skipped"] == 0
    assert ServiceCatalogItem.objects.filter(tenant=tenant_a).count() == 2

    item = ServiceCatalogItem.objects.get(tenant=tenant_a, service_code="10101")
    assert item.codigo_tributacao_nacional_iss == "10101"
    assert item.lc116_item == "1.01"
    assert "01.01.01" in str(item)
    assert "Análise" in str(item) or "desenvolvimento" in str(item).lower()

    again = materialize_national_services_for_tenant(tenant=tenant_a, only_missing=True)
    assert again["created"] == 0
    assert again["skipped"] == 2


def test_format_national_display_code():
    from apps.master_data.national_service_import import (
        format_national_display_code,
        service_catalog_display_label,
    )

    assert format_national_display_code("10301") == "01.03.01"
    assert format_national_display_code("100101") == "10.01.01"
    assert format_national_display_code("10101") == "01.01.01"
    assert (
        service_catalog_display_label(
            service_code="10301",
            codigo_tributacao_nacional_iss="10301",
            description="Processamento de dados.",
        )
        == "01.03.01 - Processamento de dados."
    )


@pytest.mark.django_db
def test_admin_materialize_get(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        email="admin@mat.local", password="Secret123!", name="Admin"
    )
    client.force_login(user)
    url = reverse("admin:master_data_servicecatalogitem_materialize_national")
    res = client.get(url)
    assert res.status_code == 200
    assert b"Materializar" in res.content
