"""Onboarding idempotente — tenant Food QA + Mercado Pago."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.food.onboarding import onboard_food_qa_tenant


class Command(BaseCommand):
    help = (
        "Provisiona tenant food-qa, usuário Hub, clientes, produto e "
        "TenantSecret Mercado Pago (opcional). Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="food-qa")
        parser.add_argument("--legal-name", default="Food QA LTDA")
        parser.add_argument("--cnpj", default="11222333000181")
        parser.add_argument("--user-email", default="qa.food@exeq.local")
        parser.add_argument("--user-password", default="Secret123!")
        parser.add_argument("--role", default="tenant_admin")
        parser.add_argument("--mp-access-token", default="")
        parser.add_argument("--mp-public-key", default="")
        parser.add_argument("--mp-webhook-secret", default="")
        parser.add_argument("--product-sku", default="QA-FOOD-01")
        parser.add_argument("--out", default="", help="Salva JSON do resultado")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "dry_run": True,
                        "slug": options["slug"],
                        "user_email": options["user_email"],
                        "has_mp_token": bool(options["mp_access_token"]),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        try:
            result = onboard_food_qa_tenant(
                slug=options["slug"],
                legal_name=options["legal_name"],
                document=options["cnpj"],
                user_email=options["user_email"],
                user_password=options["user_password"],
                role_code=options["role"],
                mp_access_token=options["mp_access_token"],
                mp_public_key=options["mp_public_key"],
                mp_webhook_secret=options["mp_webhook_secret"],
                product_sku=options["product_sku"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = result.as_dict()
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        out = (options["out"] or "").strip()
        if out:
            Path(out).write_text(text + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Onboard OK tenant={result.tenant_slug}"))
