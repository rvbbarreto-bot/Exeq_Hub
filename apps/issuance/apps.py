from django.apps import AppConfig


class IssuanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.issuance"
    label = "issuance"
    verbose_name = "Emissão NFS-e"
