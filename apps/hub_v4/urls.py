from django.urls import path

from apps.food import hub_views as food_hub
from apps.hub_v4 import views

urlpatterns = [
    path("login/", views.HubLoginView.as_view(), name="hub-v4-login"),
    path("logout/", views.hub_logout, name="hub-v4-logout"),
    path("", views.DashboardView.as_view(), name="hub-v4-dashboard"),
    path("nfse/", views.NfseListView.as_view(), name="hub-v4-nfse-list"),
    path("nfse/emitir/", views.NfseWizardView.as_view(), name="hub-v4-nfse-wizard"),
    path(
        "nfse/lookup-customer/",
        views.nfse_lookup_customer,
        name="hub-v4-nfse-lookup",
    ),
    path("nfse/<uuid:pk>/", views.NfseDetailView.as_view(), name="hub-v4-nfse-detail"),
    path(
        "nfse/<uuid:pk>/documentos/",
        views.NfseDocumentsView.as_view(),
        name="hub-v4-nfse-documents",
    ),
    path(
        "nfse/<uuid:pk>/documentos/<str:kind>/download/",
        views.nfse_document_download,
        name="hub-v4-nfse-doc-download",
    ),
    path("cobrancas/", views.ChargesListView.as_view(), name="hub-v4-charges"),
    path(
        "cobrancas/nova/",
        views.ChargeCreateView.as_view(),
        name="hub-v4-charge-new",
    ),
    path(
        "cobrancas/<uuid:pk>/",
        views.ChargeDetailView.as_view(),
        name="hub-v4-charge-detail",
    ),
    path(
        "food/pedidos/",
        food_hub.FoodOrdersListView.as_view(),
        name="hub-v4-food-orders",
    ),
    path(
        "food/pedidos/novo/",
        food_hub.FoodOrderCreateView.as_view(),
        name="hub-v4-food-order-new",
    ),
    path(
        "food/pedidos/<uuid:pk>/",
        food_hub.FoodOrderDetailView.as_view(),
        name="hub-v4-food-order-detail",
    ),
    path(
        "food/produtos/",
        food_hub.FoodProductsListView.as_view(),
        name="hub-v4-food-products",
    ),
    path(
        "food/produtos/novo/",
        food_hub.FoodProductCreateView.as_view(),
        name="hub-v4-food-product-new",
    ),
    path(
        "food/clientes/",
        food_hub.FoodCustomersListView.as_view(),
        name="hub-v4-food-customers",
    ),
    path(
        "food/clientes/novo/",
        food_hub.FoodCustomerCreateView.as_view(),
        name="hub-v4-food-customer-new",
    ),
    path(
        "food/compras/",
        food_hub.FoodPurchasesListView.as_view(),
        name="hub-v4-food-purchases",
    ),
    path(
        "food/compras/nova/",
        food_hub.FoodPurchasesNewView.as_view(),
        name="hub-v4-food-purchase-new",
    ),
    path(
        "food/producao/",
        food_hub.FoodProductionListView.as_view(),
        name="hub-v4-food-production",
    ),
    path(
        "food/inteligencia/",
        food_hub.FoodIntelligenceView.as_view(),
        name="hub-v4-food-intelligence",
    ),
    path(
        "food/regua/",
        food_hub.FoodRetentionHubView.as_view(),
        name="hub-v4-food-retention",
    ),
    path(
        "food/marketplace/",
        food_hub.FoodMarketplaceHubView.as_view(),
        name="hub-v4-food-marketplace",
    ),
    path("das/", views.DasListView.as_view(), name="hub-v4-das"),
    path("das/emitir/", views.DasEmitView.as_view(), name="hub-v4-das-emit"),
    path(
        "das/<uuid:pk>/",
        views.DasDetailView.as_view(),
        name="hub-v4-das-detail",
    ),
    path("clientes/", views.CustomersListView.as_view(), name="hub-v4-customers"),
    path("clientes/novo/", views.CustomerFormView.as_view(), name="hub-v4-customer-new"),
    path(
        "clientes/<uuid:pk>/",
        views.CustomerFormView.as_view(),
        name="hub-v4-customer-edit",
    ),
    path("empresas/", views.ProvidersListView.as_view(), name="hub-v4-providers"),
    path("empresas/nova/", views.ProviderFormView.as_view(), name="hub-v4-provider-new"),
    path(
        "empresas/<uuid:pk>/",
        views.ProviderFormView.as_view(),
        name="hub-v4-provider-edit",
    ),
    path(
        "empresas/lookup-document/",
        views.provider_lookup_document,
        name="hub-v4-provider-lookup",
    ),
    path(
        "empresa-ativa/",
        views.set_active_company,
        name="hub-v4-set-active-company",
    ),
    path("fiscal/", views.FiscalProfilesListView.as_view(), name="hub-v4-fiscal"),
    path(
        "fiscal/novo/",
        views.FiscalProfileFormView.as_view(),
        name="hub-v4-fiscal-new",
    ),
    path(
        "fiscal/<uuid:pk>/",
        views.FiscalProfileFormView.as_view(),
        name="hub-v4-fiscal-edit",
    ),
    path(
        "fiscal/regras/",
        views.TaxRulesListView.as_view(),
        name="hub-v4-tax-rules",
    ),
    path(
        "fiscal/regras/nova/",
        views.TaxRuleFormView.as_view(),
        name="hub-v4-tax-rule-new",
    ),
    path(
        "fiscal/pronto/",
        views.FiscalReadinessView.as_view(),
        name="hub-v4-fiscal-readiness",
    ),
    path(
        "fiscal/pronto/template/",
        views.FiscalTemplateApplyView.as_view(),
        name="hub-v4-fiscal-template-apply",
    ),
    path(
        "fiscal/pronto/csv/",
        views.FiscalCsvImportView.as_view(),
        name="hub-v4-fiscal-csv-import",
    ),
    path("servicos/", views.ServicesListView.as_view(), name="hub-v4-services"),
    path(
        "servicos/novo/",
        views.ServiceFormView.as_view(),
        name="hub-v4-service-new",
    ),
    path(
        "servicos/<uuid:pk>/",
        views.ServiceFormView.as_view(),
        name="hub-v4-service-edit",
    ),
    path(
        "servicos/materializar/",
        views.services_materialize,
        name="hub-v4-services-materialize",
    ),
    path("nfe/", views.NfeListView.as_view(), name="hub-v4-nfe-list"),
    path("nfe/emitir/", views.NfeEmitView.as_view(), name="hub-v4-nfe-emit"),
    path("nfe/<uuid:pk>/", views.NfeDetailView.as_view(), name="hub-v4-nfe-detail"),
    path(
        "nfe/<uuid:pk>/cancelar/",
        views.NfeCancelView.as_view(),
        name="hub-v4-nfe-cancel",
    ),
    path(
        "nfe/<uuid:pk>/cce/",
        views.NfeCceView.as_view(),
        name="hub-v4-nfe-cce",
    ),
    path(
        "nfe/<uuid:pk>/documentos/<str:kind>/download/",
        views.nfe_document_download,
        name="hub-v4-nfe-doc-download",
    ),
    path(
        "nfe/produtos/",
        views.NfeProductsListView.as_view(),
        name="hub-v4-nfe-products",
    ),
    path(
        "nfe/produtos/novo/",
        views.NfeProductFormView.as_view(),
        name="hub-v4-nfe-product-new",
    ),
    path(
        "nfe/produtos/<uuid:pk>/",
        views.NfeProductFormView.as_view(),
        name="hub-v4-nfe-product-edit",
    ),
    path("certificados/", views.CertificatesView.as_view(), name="hub-v4-certificates"),
    path("usuarios/", views.UsersListView.as_view(), name="hub-v4-users"),
    path("usuarios/convidar/", views.UserInviteView.as_view(), name="hub-v4-user-invite"),
    path(
        "usuarios/<uuid:pk>/",
        views.UserEditView.as_view(),
        name="hub-v4-user-edit",
    ),
    path("integracoes/", views.IntegrationsView.as_view(), name="hub-v4-integrations"),
    path("preferencias/", views.PreferencesView.as_view(), name="hub-v4-preferences"),
]
