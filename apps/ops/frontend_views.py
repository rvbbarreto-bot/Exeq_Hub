"""Serve o protótipo HTML/JS do Hub (mesma origem da API)."""

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views import View


FRONTEND_DIR = Path(settings.BASE_DIR) / "frontend"


class HubAppView(View):
    """GET /app/ — layout v2 com telas NFS-e e Cobranças ligadas à API."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        html = FRONTEND_DIR / "exeq_hub_layouts_v2_dados_graficos.html"
        if not html.exists():
            raise Http404("Frontend não encontrado")
        return HttpResponse(
            html.read_text(encoding="utf-8"),
            content_type="text/html; charset=utf-8",
        )


class HubFrontendFileView(View):
    """GET /app/js/... — arquivos JS do frontend (fallback se static não estiver ativo)."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, relpath: str):
        base = (FRONTEND_DIR / relpath).resolve()
        if not str(base).startswith(str(FRONTEND_DIR.resolve())):
            raise Http404()
        if not base.is_file():
            raise Http404()
        content_type = "application/javascript" if base.suffix == ".js" else "text/plain"
        return FileResponse(base.open("rb"), content_type=content_type)
