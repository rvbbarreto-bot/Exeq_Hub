"""Checklist piloto produção iFood × NFC-e."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.food.fiscal.piloto_check import run_ifood_fiscal_piloto_checks


class Command(BaseCommand):
    help = (
        "Verifica prontidão do piloto iFood fiscal (tenant, NFC-e, marketplace, beat). "
        "Use --strict-prod no host de produção."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            help="Slug do tenant piloto (1 loja SP).",
        )
        parser.add_argument(
            "--strict-prod",
            action="store_true",
            help="Falha se DEBUG, CELERY eager ou ALLOWED_HOSTS de lab.",
        )
        parser.add_argument(
            "--out",
            default=".storage/ifood_fiscal_piloto_check.json",
            help="JSON de evidência",
        )

    def handle(self, *args, **options):
        slug = (options["tenant"] or "").strip()
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {slug}") from exc

        report = run_ifood_fiscal_piloto_checks(
            tenant=tenant,
            strict_prod=bool(options["strict_prod"]),
        )
        report["generated_at"] = timezone.now().isoformat()
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"iFood fiscal piloto check: {out}"))
        for c in report["checks"]:
            mark = "OK" if c["ok"] else "FAIL"
            style = self.style.SUCCESS if c["ok"] else self.style.ERROR
            req = " *" if c.get("required", True) and not c["ok"] else ""
            self.stdout.write(style(f"  [{mark}] {c['id']}: {c['detail']}{req}"))

        if report["ready_for_pilot"]:
            self.stdout.write(self.style.SUCCESS("Pronto para piloto (checks obrigatórios OK)."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Pendências obrigatórias: {report['summary']['fail_required']}"
                )
            )
        for step in report.get("next_steps", []):
            self.stdout.write(f"  -> {step}")

        if options["strict_prod"] and not report["ready_for_pilot"]:
            raise SystemExit(1)
