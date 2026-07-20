from django.contrib import admin

from apps.ops.models import OutboxMessage, StoredFile


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):
    list_display = ("event_type", "status", "tenant", "attempts", "available_at")
    list_filter = ("status", "event_type")


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ("purpose", "backend", "object_key", "tenant", "size_bytes")
    search_fields = ("object_key", "purpose", "checksum_sha256")
