"""Gate Fase 2 — iFood HTTP + cert + CSC."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.food.fiscal.phase2_prep import run_phase2_readiness


class Command(BaseCommand):
    help = "Lista blockers Fase 2 (cert, CSC, iFood HTTP, de-para) sem alterar dados."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument(
            "--out",
            default=".storage/ifood_fiscal_phase2_{tenant}.json",
        )

    def handle(self, *args, **options):
        slug = (options["tenant"] or "").strip()
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            raise CommandError(f"Tenant nao encontrado: {slug}")

        report = run_phase2_readiness(tenant=tenant)
        report["command_finished_at"] = timezone.now().isoformat()

        out = Path(options["out"].format(tenant=slug))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Fase 2 readiness: {out}"))
        for c in report["checks"]:
            mark = "OK" if c["ok"] else "BLOCK" if c["blocker"] else "WARN"
            style = self.style.SUCCESS if c["ok"] else self.style.ERROR if c["blocker"] else self.style.WARNING
            self.stdout.write(style(f"  [{mark}] {c['id']}: {c['detail']}"))

        if report["ready_for_phase2"]:
            self.stdout.write(self.style.SUCCESS("Pronto para iniciar Fase 2 (blockers OK)."))
        else:
            self.stdout.write(
                self.style.WARNING(f"Blockers pendentes: {report['summary']['blockers']}")
            )
        for step in report.get("ops_manual", []):
            self.stdout.write(f"  -> {step}")
