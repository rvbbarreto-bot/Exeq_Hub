from rest_framework.routers import DefaultRouter

from apps.issuance.views import NfIssueViewSet
from apps.issuance.webhook_views import FocusNfseWebhookView
from django.urls import path

router = DefaultRouter()
router.register("nf-issue", NfIssueViewSet, basename="nf-issue")

urlpatterns = [
    path(
        "webhooks/focus-nfse",
        FocusNfseWebhookView.as_view(),
        name="webhooks-focus-nfse",
    ),
    *router.urls,
]
