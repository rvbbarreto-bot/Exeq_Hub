"""OpenAPI — NF-e de entrada (S7)."""

from apps.ops.openapi_views import load_openapi_dict

ENTRADA_PATHS = (
    "/nfe/entrada/",
    "/nfe/entrada/sync/",
    "/nfe/entrada/distribution/status/",
    "/nfe/entrada/distribution/config/",
    "/nfe/entrada/{id}/",
    "/nfe/entrada/{id}/manifest/",
    "/nfe/entrada/{id}/xml/",
)


def test_openapi_nfe_entrada_fragment_merged():
    load_openapi_dict.cache_clear()
    spec = load_openapi_dict()
    paths = spec["paths"]
    for p in ENTRADA_PATHS:
        assert p in paths, f"missing {p}"

    tags = {t["name"] if isinstance(t, dict) else t for t in spec.get("tags") or []}
    assert "nfe_entrada" in tags

    manifest_path = paths["/nfe/entrada/{id}/manifest/"]["post"]
    assert manifest_path["tags"] == ["nfe_entrada"]
    body_schema = (
        manifest_path["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    )
    assert body_schema.endswith("NfeEntradaManifestRequest")

    desc = spec.get("info", {}).get("description") or ""
    assert "NF-e de entrada" in desc
    assert "openapi-nfe-entrada-v1.yaml" in desc

    load_openapi_dict.cache_clear()
