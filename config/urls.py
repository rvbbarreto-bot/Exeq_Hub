from django.contrib import admin
from django.urls import include, path

from apps.accounts.certificate_views import (
    RegisterFocusEmpresaView,
    SetFocusTokenView,
    UploadCertificateView,
)
from apps.accounts.focus_municipio_views import FocusMunicipioView
from apps.accounts.proxy_views import ElectronicProxyListCreateView
from apps.ops.frontend_views import HubAppView, HubFrontendFileView
from apps.ops.openapi_views import OpenAPIJsonView

admin.site.site_header = "EXEQ Hub — Admin QA"
admin.site.site_title = "EXEQ Hub"
admin.site.index_title = "Emissão NFS-e e cadastros"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("app/", HubAppView.as_view(), name="hub-app"),
    path("app/<path:relpath>", HubFrontendFileView.as_view(), name="hub-app-file"),
    path("api/v1/openapi.json", OpenAPIJsonView.as_view()),
    path("api/v1/auth/", include("apps.accounts.urls")),
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
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.das.urls")),
    path("api/v1/", include("apps.channel.urls")),
]
