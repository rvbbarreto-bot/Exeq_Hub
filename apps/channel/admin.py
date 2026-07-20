from django.contrib import admin

from apps.channel.models import ChannelNotification, ChannelSession


@admin.register(ChannelSession)
class ChannelSessionAdmin(admin.ModelAdmin):
    list_display = ("phone_e164", "status", "tenant", "last_message_at")


@admin.register(ChannelNotification)
class ChannelNotificationAdmin(admin.ModelAdmin):
    list_display = ("phone_e164", "event_type", "status", "tenant")
