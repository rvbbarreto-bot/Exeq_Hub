from pathlib import Path

import openpyxl
import pytest

from apps.master_data.models import NbsCatalogVersion, NbsItem
from apps.master_data.nbs_import import (
    NbsImportError,
    format_nbs_display_code,
    import_nbs_xlsx,
    normalize_nbs_code,
    publish_nbs_version,
    search_nbs,
)
from apps.master_data.nbs_resolution import resolve_codigo_nbs
from apps.master_data.services import create_service


def _write_nbs_xlsx(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LISTA.NBS_v2.0"
    ws.append(["CÓDIGO NBS", "DESCRIÇÃO"])
    ws.append(["1.1501.30.00", "Serviços de consultoria em tecnologia da informação"])
    ws.append([115022000, "Serviços de hospedagem na internet"])
    wb.save(path)


@pytest.mark.django_db
def test_import_nbs_xlsx_publishes(tmp_path):
    xlsx = tmp_path / "anexo_b_nbs.xlsx"
    _write_nbs_xlsx(xlsx)
    version = import_nbs_xlsx(
        path=xlsx, version_label="NBS_v2.0-2026-test", publish=True
    )
    assert version.status == NbsCatalogVersion.Status.PUBLISHED
    assert version.row_count == 2
    codes = set(NbsItem.objects.filter(version=version).values_list("codigo", flat=True))
    assert codes == {"115013000", "115022000"}


@pytest.mark.django_db
def test_import_nbs_duplicate_version_label(tmp_path):
    xlsx = tmp_path / "anexo_b_nbs.xlsx"
    _write_nbs_xlsx(xlsx)
    import_nbs_xlsx(path=xlsx, version_label="nbs-v1", publish=True)
    with pytest.raises(NbsImportError):
        import_nbs_xlsx(path=xlsx, version_label="nbs-v1", publish=False)


@pytest.mark.django_db
def test_publish_nbs_supersedes_previous(tmp_path):
    xlsx = tmp_path / "anexo_b_nbs.xlsx"
    _write_nbs_xlsx(xlsx)
    v1 = import_nbs_xlsx(path=xlsx, version_label="nbs-old", publish=True)
    xlsx2 = tmp_path / "anexo_b_nbs2.xlsx"
    _write_nbs_xlsx(xlsx2)
    v2 = import_nbs_xlsx(path=xlsx2, version_label="nbs-new", publish=True)
    v1.refresh_from_db()
    assert v1.status == NbsCatalogVersion.Status.SUPERSEDED
    assert v2.status == NbsCatalogVersion.Status.PUBLISHED


@pytest.mark.django_db
def test_search_nbs_by_code_and_description(tmp_path):
    xlsx = tmp_path / "anexo_b_nbs.xlsx"
    _write_nbs_xlsx(xlsx)
    import_nbs_xlsx(path=xlsx, version_label="nbs-search", publish=True)

    by_code = search_nbs(query="115013", limit=10)
    assert len(by_code) == 1
    assert by_code[0]["codigo"] == "115013000"

    by_desc = search_nbs(query="hospedagem", limit=10)
    assert len(by_desc) == 1
    assert by_desc[0]["codigo"] == "115022000"


@pytest.mark.django_db
def test_nbs_search_api(api_client, auth_header, tmp_path):
    xlsx = tmp_path / "anexo_b_nbs.xlsx"
    _write_nbs_xlsx(xlsx)
    import_nbs_xlsx(path=xlsx, version_label="nbs-api", publish=True)

    res = api_client.get(
        "/api/v1/master-data/nbs/search?q=115022&limit=5",
        **auth_header,
    )
    assert res.status_code == 200
    assert res.data["count"] == 1
    assert res.data["results"][0]["codigo"] == "115022000"


@pytest.mark.django_db
def test_create_service_links_nbs(tenant_a, tmp_path):
    xlsx = tmp_path / "anexo_b_nbs.xlsx"
    _write_nbs_xlsx(xlsx)
    import_nbs_xlsx(path=xlsx, version_label="nbs-svc", publish=True)

    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Consultoria TI",
        codigo_nbs="115013000",
    )
    assert service.codigo_nbs == "115013000"
    assert service.nbs_item is not None
    assert service.nbs_item.codigo == "115013000"


@pytest.mark.django_db
def test_resolve_codigo_nbs_priority():
    service = type(
        "Svc",
        (),
        {"codigo_nbs": "111111111", "nbs_item": None},
    )()
    assert (
        resolve_codigo_nbs(
            service=service,
            params={"codigo_nbs": "333333333"},
            draft_emission={"codigo_nbs": "222222222"},
        )
        == "222222222"
    )
    assert (
        resolve_codigo_nbs(
            service=service,
            params={"codigo_nbs": "333333333"},
            draft_emission={},
        )
        == "333333333"
    )
    assert resolve_codigo_nbs(service=service, params={}, draft_emission={}) == "111111111"


def test_normalize_and_format_nbs_code():
    assert normalize_nbs_code("1.1501.30.00") == "115013000"
    assert format_nbs_display_code("115013000") == "1.1501.30.00"
