"""Import CSV multi-IBGE de regras ISS. Idempotente."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Tenant
from apps.fiscal.models import FiscalProfile
from apps.fiscal.templates_factory import import_rules_csv


class Command(BaseCommand):
    help = "Importa regras ISS municipais via CSV (multi-IBGE). Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--fiscal-profile", required=True)
        parser.add_argument("--file", default="", help="Arquivo CSV UTF-8")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--out", default="")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            raise CommandError(f"Tenant não encontrado: {options['tenant']}")
        profile = FiscalProfile.objects.filter(
            tenant=tenant, name=options["fiscal_profile"]
        ).first()
        if profile is None:
            raise CommandError(
                f"Perfil fiscal não encontrado: {options['fiscal_profile']}"
            )

        path = (options["file"] or "").strip()
        if not path:
            raise CommandError("Informe --file com o CSV.")
        csv_text = Path(path).read_text(encoding="utf-8-sig")

        if options["dry_run"]:
            from apps.fiscal.multimunicipio import parse_csv_preview

            rows = parse_csv_preview(csv_text)
            payload = {
                "dry_run": True,
                "rows": len(rows),
                "ibge_codes": sorted({r.ibge_code for r in rows}),
            }
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        try:
            result = import_rules_csv(
                tenant=tenant, profile=profile, csv_text=csv_text
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        text = json.dumps(result, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        out = (options["out"] or "").strip()
        if out:
            Path(out).write_text(text + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Import OK: {len(result['applied_service_codes'])} regra(s), "
                f"IBGE {', '.join(result.get('ibge_codes') or [])}"
            )
        )
