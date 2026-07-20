"""Cria o usuário Emissor e o grupo com permissões do fluxo NFS-e."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

# Modelos necessários para configurar cadastros + emitir NFS-e no Admin.
EMISSOR_PERMISSION_SPECS = (
    # Contas — tenant (seleção / ajuste mínimo)
    ("accounts", "tenant", ("view", "add", "change")),
    # Cadastros
    ("master_data", "provider", ("view", "add", "change")),
    ("master_data", "customer", ("view", "add", "change")),
    ("master_data", "servicecatalogitem", ("view", "add", "change")),
    # Fiscal
    ("fiscal", "fiscalprofile", ("view", "add", "change")),
    ("fiscal", "taxrulecatalog", ("view", "add", "change")),
    ("fiscal", "municipaltaxrule", ("view", "add", "change")),
    # Emissão
    ("issuance", "nfissue", ("view", "add", "change")),
    ("issuance", "nfissueevent", ("view",)),
    ("issuance", "nfartifact", ("view",)),
    ("issuance", "fiscalrulesnapshot", ("view",)),
    # Arquivos / certificado (configuração da empresa)
    ("ops", "storedfile", ("view",)),
    ("accounts", "digitalcertificate", ("view", "add", "change")),
)

GROUP_NAME = "Emissor NFS-e"
DEFAULT_EMAIL = "emissor@exeq.local"
DEFAULT_NAME = "Emissor"
DEFAULT_PASSWORD = "EmissorNf123!"


class Command(BaseCommand):
    help = "Cria/atualiza o usuário Emissor com permissões só do fluxo de emissão NFS-e."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--name", default=DEFAULT_NAME)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)

    def handle(self, *args, **options):
        perms = self._resolve_permissions()
        group, _ = Group.objects.get_or_create(name=GROUP_NAME)
        group.permissions.set(perms)

        User = get_user_model()
        email = options["email"]
        password = options["password"]
        name = options["name"]
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": name,
                "is_active": True,
                "is_staff": True,
                "is_superuser": False,
                "is_platform_admin": False,
            },
        )
        user.name = name
        user.is_active = True
        user.is_staff = True
        user.is_superuser = False
        user.is_platform_admin = False
        user.set_password(password)
        user.save()
        user.groups.set([group])
        user.user_permissions.clear()

        action = "criado" if created else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"Usuário {action}: {user.name} <{user.email}>"))
        self.stdout.write(f"  Grupo: {GROUP_NAME} ({perms.count()} permissões)")
        self.stdout.write(f"  Senha: {password}")
        self.stdout.write("  Acesso: http://127.0.0.1:8000/admin/")

    def _resolve_permissions(self):
        collected = []
        missing = []
        for app_label, model, actions in EMISSOR_PERMISSION_SPECS:
            try:
                ct = ContentType.objects.get(app_label=app_label, model=model)
            except ContentType.DoesNotExist:
                missing.append(f"{app_label}.{model}")
                continue
            for action in actions:
                codename = f"{action}_{model}"
                try:
                    collected.append(Permission.objects.get(content_type=ct, codename=codename))
                except Permission.DoesNotExist:
                    missing.append(f"{app_label}.{codename}")
        if missing:
            self.stderr.write(
                self.style.WARNING("Permissões/modelos não encontrados: " + ", ".join(missing))
            )
        return Permission.objects.filter(pk__in=[p.pk for p in collected])
