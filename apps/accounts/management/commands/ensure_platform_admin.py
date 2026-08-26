"""Garante o superusuário único de plataforma (Admin clássico Django)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import TenantMembership

DEFAULT_EMAIL = "admin@local"
DEFAULT_NAME = "admin"
DEFAULT_PASSWORD = "admin"


class Command(BaseCommand):
    help = (
        "Cria/atualiza Exeq_admin (superuser, poder total no Django Admin clássico). "
        "Com --wipe-others remove os demais usuários e memberships."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--name", default=DEFAULT_NAME)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument(
            "--wipe-others",
            action="store_true",
            help="Apaga todos os outros usuários e todos os TenantMemberships.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options["email"] or DEFAULT_EMAIL).strip().lower()
        name = options["name"] or DEFAULT_NAME
        password = options["password"] or DEFAULT_PASSWORD

        if options["wipe_others"]:
            n_m = TenantMembership.objects.count()
            TenantMembership.objects.all().delete()
            n_u = User.objects.exclude(email__iexact=email).count()
            User.objects.exclude(email__iexact=email).delete()
            self.stdout.write(f"Removidos memberships={n_m} outros_users={n_u}")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": name,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
                "is_platform_admin": True,
            },
        )
        user.name = name
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.is_platform_admin = True
        user.set_password(password)
        user.save()

        # Plataforma não opera no Hub com membership; só Admin.
        # Clientes = User + TenantMembership criados por este admin.
        TenantMembership.objects.filter(user=user).delete()

        action = "criado" if created else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"Exeq_admin {action}: {email}"))
        self.stdout.write(f"  Admin clássico: /admin/")
        self.stdout.write(f"  Hub V4 (cliente): /hub/")
        self.stdout.write(f"  Usuários no sistema: {User.objects.count()}")
