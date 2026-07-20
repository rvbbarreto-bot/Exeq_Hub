from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.channel.views import ChannelNotifyView, ChannelSessionViewSet, EvolutionWebhookView

router = DefaultRouter()
router.register("channel/sessions", ChannelSessionViewSet, basename="channel-sessions")

urlpatterns = [
    *router.urls,
    path("webhooks/evolution", EvolutionWebhookView.as_view(), name="webhooks-evolution"),
    path("channel/notify", ChannelNotifyView.as_view(), name="channel-notify"),
]
