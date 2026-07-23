from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    label = "billing"
    verbose_name = "Cobrança"

    def ready(self):
        from shared.security_checks import assert_secure_runtime_settings

        assert_secure_runtime_settings()
