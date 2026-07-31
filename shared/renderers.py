"""Renderers para downloads binários (evita 406 do DRF com Accept: application/pdf)."""

from __future__ import annotations

import json

from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.utils.encoders import JSONEncoder


class PDFBinaryRenderer(BaseRenderer):
    """Aceita Accept: application/pdf (Hub) e devolve bytes ou JSON de erro."""

    media_type = "application/pdf"
    format = "pdf"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)
        # Erro DRF Response com Accept: application/pdf
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        if response is not None:
            response["Content-Type"] = "application/json"
        return json.dumps(data, cls=JSONEncoder, ensure_ascii=False).encode("utf-8")


class AnyBinaryRenderer(BaseRenderer):
    """Fallback amplo (*/*) para negociação quando o cliente manda só application/pdf."""

    media_type = "*/*"
    format = "bin"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        if response is not None:
            response["Content-Type"] = "application/json"
        return json.dumps(data, cls=JSONEncoder, ensure_ascii=False).encode("utf-8")


# FileResponse (sucesso) não passa pelo render; erros JSON precisam negociar Accept.
PDF_DOWNLOAD_RENDERERS = [PDFBinaryRenderer, JSONRenderer, AnyBinaryRenderer]
