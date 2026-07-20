from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Contas e acesso"

    def ready(self) -> None:
        from django.db.backends.signals import connection_created

        from shared.rls import set_rls

        def _default_bypass(sender, connection, **kwargs):  # noqa: ARG001
            if connection.vendor == "postgresql":
                set_rls(bypass=True)

        connection_created.connect(_default_bypass, dispatch_uid="exeq_rls_default_bypass")
