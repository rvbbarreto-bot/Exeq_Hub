"""Provisiona matriz fiscal EXEQ Lab (catálogo + regras Atibaia). Idempotente."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.provision_exeq_lab import provision_exeq_lab_fiscal


class Command(BaseCommand):
    help = (
        "Provisiona serviços + regras ISS Atibaia para tenant exeq-lab "
        "(matriz Sprint A). Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="exeq-lab")
        parser.add_argument("--cnpj", default="37229907000137")
        parser.add_argument("--fiscal-profile", default="SN-EXEQ-LAB")
        parser.add_argument(
            "--template",
            default="exeq-lab-sn-v1",
            help="Template municipal embutido",
        )
        parser.add_argument(
            "--skip-rules",
            action="store_true",
            help="Só catálogo de serviços, sem publicar regras",
        )
        parser.add_argument("--out", default="", help="Salva JSON do resultado")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "dry_run": True,
                        "tenant": options["tenant"],
                        "template": options["template"],
                        "fiscal_profile": options["fiscal_profile"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        try:
            result = provision_exeq_lab_fiscal(
                tenant_slug=options["tenant"],
                fiscal_profile_name=options["fiscal_profile"],
                cnpj=options["cnpj"],
                template_id=options["template"],
                apply_rules=not options["skip_rules"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = result.as_dict()
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        out = (options["out"] or "").strip()
        if out:
            Path(out).write_text(text + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Provision OK tenant={result.tenant_slug} "
                f"services+={len(result.services_created)} "
                f"rules={len(result.template_applied)}"
            )
        )
