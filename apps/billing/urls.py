from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.billing.cancel_views import CancelMotivosView
from apps.billing.provider_views import (
    BillingProviderView,
    InterCredentialsView,
    InterTestConnectionView,
    InterWebhookRetryView,
    InterWebhookView,
    TokenProviderCredentialsView,
)
from apps.billing.preset_views import BillingPresetView
from apps.billing.views import ChargeViewSet, GatewayWebhookView, WebhookInboxViewSet

router = DefaultRouter()
router.register("charges", ChargeViewSet, basename="charges")
router.register("webhooks", WebhookInboxViewSet, basename="webhooks")

urlpatterns = [
    path("webhooks/gateway", GatewayWebhookView.as_view(), name="webhooks-gateway"),
    path("billing/provider", BillingProviderView.as_view(), name="billing-provider"),
    path("billing/presets", BillingPresetView.as_view(), name="billing-presets"),
    path(
        "billing/cancel-motivos",
        CancelMotivosView.as_view(),
        name="billing-cancel-motivos",
    ),
    path(
        "billing/providers/inter/credentials",
        InterCredentialsView.as_view(),
        name="billing-inter-credentials",
    ),
    path(
        "billing/providers/inter/test-connection",
        InterTestConnectionView.as_view(),
        name="billing-inter-test-connection",
    ),
    path(
        "billing/providers/inter/webhook",
        InterWebhookView.as_view(),
        name="billing-inter-webhook",
    ),
    path(
        "billing/providers/inter/webhook/callbacks/retry",
        InterWebhookRetryView.as_view(),
        name="billing-inter-webhook-retry",
    ),
    path(
        "billing/providers/<str:provider>/credentials",
        TokenProviderCredentialsView.as_view(),
        name="billing-token-credentials",
    ),
    *router.urls,
]
