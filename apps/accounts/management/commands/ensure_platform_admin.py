"""Garante o superusuário único de plataforma (Admin clássico Django)."""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.accounts.models import TenantMembership
from apps.accounts.plan_services import ensure_system_plans
from apps.accounts.services import ensure_system_roles

DEFAULT_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "admin@local")
DEFAULT_NAME = os.environ.get("PLATFORM_ADMIN_NAME", "admin")
DEFAULT_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "admin")


class Command(BaseCommand):
    help = (
        "Cria/atualiza o superuser de plataforma (Django Admin). "
        "Com --wipe-others remove os demais usuários e memberships. "
        "Com --flush-lab apaga todos os dados do BD (lab) e recria catálogos mínimos."
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
        parser.add_argument(
            "--flush-lab",
            action="store_true",
            help="flush no Postgres (apaga tenants, guias, NF-e, etc.) antes de criar o admin.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options["email"] or DEFAULT_EMAIL).strip().lower()
        name = options["name"] or DEFAULT_NAME
        password = options["password"] or DEFAULT_PASSWORD

        if options["flush_lab"]:
            self.stdout.write("flush: apagando todos os registros do BD…")
            call_command("flush", verbosity=0, interactive=False)
            ensure_system_roles()
            ensure_system_plans()
            self.stdout.write(self.style.WARNING("BD zerado; roles e planos seed recriados."))

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
        TenantMembership.objects.filter(user=user).delete()

        action = "criado" if created else "atualizado"
        self.stdout.write(self.style.SUCCESS(f"Exeq_admin {action}: {email}"))
        self.stdout.write("  Admin clássico: /admin/")
        self.stdout.write("  Hub V4 (cliente): /hub/ — crie tenant + usuários pelo Admin")
        self.stdout.write(f"  Usuários no sistema: {User.objects.count()}")
