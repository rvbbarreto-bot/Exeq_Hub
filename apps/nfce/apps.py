from django.apps import AppConfig


class NfceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nfce"
    label = "nfce"
    verbose_name = "Emissão NFC-e (PDV)"
