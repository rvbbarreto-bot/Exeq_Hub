from django.apps import AppConfig


class NfeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nfe"
    label = "nfe"
    verbose_name = "Emissão NF-e (produto)"
