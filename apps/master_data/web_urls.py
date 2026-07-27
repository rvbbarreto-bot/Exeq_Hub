"""Telas Django oficiais de Prestador/Tomador (/cadastros/)."""

from django.urls import path

from apps.master_data import web_views

urlpatterns = [
    path("login/", web_views.CadastroLoginView.as_view(), name="cadastro-login"),
    path("logout/", web_views.cadastro_logout, name="cadastro-logout"),
    path("", web_views.CadastroHomeView.as_view(), name="cadastro-home"),
    path("providers/", web_views.ProviderListView.as_view(), name="cadastro-provider-list"),
    path(
        "providers/novo/",
        web_views.ProviderFormView.as_view(),
        name="cadastro-provider-new",
    ),
    path(
        "providers/<uuid:pk>/",
        web_views.ProviderFormView.as_view(),
        name="cadastro-provider-edit",
    ),
    path("customers/", web_views.CustomerListView.as_view(), name="cadastro-customer-list"),
    path(
        "customers/novo/",
        web_views.CustomerFormView.as_view(),
        name="cadastro-customer-new",
    ),
    path(
        "customers/<uuid:pk>/",
        web_views.CustomerFormView.as_view(),
        name="cadastro-customer-edit",
    ),
    path(
        "lookup/provider/",
        web_views.cadastro_lookup_ajax,
        {"entity_kind": "provider"},
        name="cadastro-lookup-provider",
    ),
    path(
        "lookup/customer/",
        web_views.cadastro_lookup_ajax,
        {"entity_kind": "customer"},
        name="cadastro-lookup-customer",
    ),
]
