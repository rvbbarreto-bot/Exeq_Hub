"""Serve OpenAPI v4 + fragmento NF-e (YAML → JSON) sem dependência pesada."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except Exception:
        return None


def _merge_openapi(base: dict, fragment: dict) -> dict:
    """Merge paths/tags/schemas do fragmento NF-e no documento principal."""
    if not isinstance(fragment, dict):
        return base
    paths = base.setdefault("paths", {})
    for k, v in (fragment.get("paths") or {}).items():
        paths[k] = v
    tags = base.setdefault("tags", [])
    if isinstance(tags, list):
        existing = {t.get("name") if isinstance(t, dict) else t for t in tags}
        for t in fragment.get("tags") or []:
            name = t.get("name") if isinstance(t, dict) else t
            if name not in existing:
                tags.append(t)
                existing.add(name)
    base_comp = base.setdefault("components", {})
    frag_comp = fragment.get("components") or {}
    for section in ("schemas", "parameters", "responses", "securitySchemes"):
        if section in frag_comp:
            target = base_comp.setdefault(section, {})
            if isinstance(target, dict) and isinstance(frag_comp[section], dict):
                target.update(frag_comp[section])
    # bump note in description if nfe paths present
    info = base.setdefault("info", {})
    desc = str(info.get("description") or "")
    if "/nfe/gate/" in paths and "NF-e modelo 55" not in desc:
        info["description"] = (
            desc.rstrip()
            + "\n    NF-e modelo 55 (paths /nfe/*; feature flag NFE_ENABLED; ver openapi-nfe-v1.yaml).\n"
        )
    return base


@lru_cache(maxsize=1)
def load_openapi_dict() -> dict:
    path = Path(settings.BASE_DIR) / "Docs" / "openapi-v4.yaml"
    data = _load_yaml(path)
    if data is None:
        # fallback mínimo se PyYAML ausente — paths críticos
        data = {
            "openapi": "3.0.3",
            "info": {"title": "EXEQ Hub API", "version": "4.1.0-draft"},
            "paths": {
                "/das/guias/": {},
                "/charges/": {},
                "/electronic-proxies/": {},
                "/openapi.json": {},
                "/nfe/gate/": {},
            },
            "components": {"schemas": {}},
            "tags": [{"name": "nfe"}],
        }
    if not isinstance(data, dict):
        raise RuntimeError("openapi-v4.yaml inválido")

    nfe_path = Path(settings.BASE_DIR) / "Docs" / "openapi-nfe-v1.yaml"
    if nfe_path.exists():
        nfe = _load_yaml(nfe_path)
        if isinstance(nfe, dict):
            data = _merge_openapi(data, nfe)
        elif nfe is not None:
            # YAML valid load but wrong root — ignore, keep base
            pass
    return data


class OpenAPIJsonView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(load_openapi_dict())
