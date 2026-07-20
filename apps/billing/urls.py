from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.billing.views import ChargeViewSet, GatewayWebhookView, WebhookInboxViewSet

router = DefaultRouter()
router.register("charges", ChargeViewSet, basename="charges")
router.register("webhooks", WebhookInboxViewSet, basename="webhooks")

urlpatterns = [
    path("webhooks/gateway", GatewayWebhookView.as_view(), name="webhooks-gateway"),
    *router.urls,
]
