from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.certificate_views import (
    DigitalCertificateListView,
    RegisterFocusEmpresaView,
    SetFocusTokenView,
    UploadCertificateView,
)
from apps.accounts.focus_municipio_views import FocusMunicipioView
from apps.accounts.proxy_views import ElectronicProxyListCreateView
from apps.ops.openapi_views import OpenAPIJsonView

# Admin clássico Django (plataforma / Exeq_admin). Cliente usa Hub V4.
admin.site.site_header = "EXEQ Hub — Plataforma"
admin.site.site_title = "EXEQ Admin"
admin.site.index_title = "Gestão de plataforma (Exeq_admin)"

# Legados descontinuados → Hub V4
_legacy_to_hub = RedirectView.as_view(url="/hub/", permanent=False)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("hub/", include("apps.hub_v4.urls")),
    # Descontinuados (SPA + cadastros ilha)
    path("cadastros/", _legacy_to_hub),
    path("cadastros/<path:unused>", _legacy_to_hub),
    path("app/", _legacy_to_hub, name="hub-app"),
    path("app/<path:unused>", _legacy_to_hub, name="hub-app-file"),
    path("", RedirectView.as_view(url="/hub/", permanent=False)),
    path("api/v1/openapi.json", OpenAPIJsonView.as_view()),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/certificates/", DigitalCertificateListView.as_view()),
    path("api/v1/certificates/upload", UploadCertificateView.as_view()),
    path("api/v1/electronic-proxies/", ElectronicProxyListCreateView.as_view()),
    path("api/v1/integrations/focus/token", SetFocusTokenView.as_view()),
    path("api/v1/integrations/focus/empresas", RegisterFocusEmpresaView.as_view()),
    path(
        "api/v1/integrations/focus/municipios/<str:ibge_code>",
        FocusMunicipioView.as_view(),
    ),
    path("api/v1/", include("apps.master_data.urls")),
    path("api/v1/", include("apps.fiscal.urls")),
    path("api/v1/", include("apps.issuance.urls")),
    path("api/v1/", include("apps.nfe.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.das.urls")),
    path("api/v1/", include("apps.channel.urls")),
    path("api/v1/", include("apps.scheduling.urls")),
    path("api/v1/", include("apps.food.urls")),
]
