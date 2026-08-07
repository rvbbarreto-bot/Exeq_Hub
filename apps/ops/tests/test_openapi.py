import sys

import pytest

from apps.ops.openapi_views import load_openapi_dict


REQUIRED_PATHS = (
    "/das/guias/",
    "/das/guias/{id}/pdf/",
    "/charges/",
    "/charges/summary/",
    "/charges/{id}/pdf/",
    "/billing/provider",
    "/billing/cancel-motivos",
    "/electronic-proxies/",
    "/certificates/",
    "/certificates/upload",
    "/openapi.json",
    "/nf-issue/",
    "/nfe/gate/",
    "/nfe/invoices/",
)


def test_openapi_yaml_loads_with_required_paths():
    load_openapi_dict.cache_clear()
    spec = load_openapi_dict()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["version"].startswith("4.")
    paths = spec["paths"]
    for p in REQUIRED_PATHS:
        assert p in paths, f"missing {p}"
    schemas = spec["components"]["schemas"]
    assert "GuiaCreate" in schemas
    assert "ChargeCreate" in schemas
    assert "Charge" in schemas
    assert "has_boleto_pdf" in schemas["Charge"]["properties"]
    assert "ElectronicProxyCreate" in schemas
    sync_path = paths.get("/charges/{id}/sync/") or paths.get("/charges/{id}/sync")
    assert sync_path is not None
    assert "get" not in sync_path
    assert "post" in sync_path


@pytest.mark.django_db
def test_openapi_json_endpoint(api_client):
    load_openapi_dict.cache_clear()
    response = api_client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert "/das/guias/" in response.data["paths"]


def test_openapi_fallback_when_yaml_fails(monkeypatch):
    load_openapi_dict.cache_clear()

    class BoomYaml:
        @staticmethod
        def safe_load(_text):
            raise RuntimeError("yaml broken")

    monkeypatch.setitem(sys.modules, "yaml", BoomYaml)
    spec = load_openapi_dict()
    assert spec["info"]["version"] == "4.1.0-draft"
    assert "/electronic-proxies/" in spec["paths"]
    assert "/nfe/gate/" in spec["paths"]
    load_openapi_dict.cache_clear()


def test_openapi_invalid_document_raises(monkeypatch, settings, tmp_path):
    load_openapi_dict.cache_clear()
    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "openapi-v4.yaml").write_text("- not-a-mapping\n", encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="inválido"):
        load_openapi_dict()
    load_openapi_dict.cache_clear()
