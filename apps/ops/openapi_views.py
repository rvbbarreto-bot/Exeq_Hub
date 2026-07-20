"""Serve OpenAPI v4 (YAML → JSON) sem dependência pesada."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@lru_cache(maxsize=1)
def load_openapi_dict() -> dict:
    path = Path(settings.BASE_DIR) / "Docs" / "openapi-v4.yaml"
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        # fallback mínimo se PyYAML ausente — paths críticos
        data = {
            "openapi": "3.0.3",
            "info": {"title": "EXEQ Hub API", "version": "4.1.0-draft"},
            "paths": {
                "/das/guias/": {},
                "/charges/": {},
                "/electronic-proxies/": {},
                "/openapi.json": {},
            },
        }
    if not isinstance(data, dict):
        raise RuntimeError("openapi-v4.yaml inválido")
    return data


class OpenAPIJsonView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(load_openapi_dict())
