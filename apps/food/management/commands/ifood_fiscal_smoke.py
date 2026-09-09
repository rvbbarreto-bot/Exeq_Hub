"""Smoke QA Fase 1 — iFood fiscal stub."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.food.fiscal.smoke_suite import run_ifood_fiscal_smoke_suite


class Command(BaseCommand):
    help = "Executa smoke QA (sucesso + exceção) iFood fiscal stub no tenant informado."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Slug tenant (ex.: ALE)")
        parser.add_argument(
            "--phase",
            default="all",
            choices=("1", "1b", "all"),
            help="Fase do smoke: 1 emissão, 1b cancel PO-3, all ambas",
        )
        parser.add_argument(
            "--out",
            default=".storage/ifood_fiscal_smoke_{tenant}.json",
            help="JSON de evidência (use {tenant} no path)",
        )

    def handle(self, *args, **options):
        slug = (options["tenant"] or "").strip()
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            raise CommandError(f"Tenant não encontrado: {slug}")

        phase = options["phase"]
        report = run_ifood_fiscal_smoke_suite(tenant=tenant, phase=phase)
        report["command_finished_at"] = timezone.now().isoformat()

        out_tpl = options["out"]
        out_path = Path(out_tpl.format(tenant=slug))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Smoke iFood fiscal: {out_path}"))
        for c in report["cases"]:
            mark = "PASS" if c.get("passed") else "FAIL"
            style = self.style.SUCCESS if c.get("passed") else self.style.ERROR
            self.stdout.write(style(f"  [{mark}] {c['id']}: {c['title']}"))
            if c.get("error"):
                self.stdout.write(f"         {c['error']}")

        s = report["summary"]
        if report.get("phase_complete"):
            self.stdout.write(self.style.SUCCESS(f"{report['phase']}: {s['passed']}/{s['total']} OK"))
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"Falhas: {s['failed']} ({', '.join(s['failed_ids'])})"
                )
            )
            raise SystemExit(1)
