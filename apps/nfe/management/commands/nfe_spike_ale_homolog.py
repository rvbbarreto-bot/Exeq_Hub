"""Spike HTTP homolog SP — tenant piloto ALE (61536366000174).

Dry-run (assina sem POST):
  python manage.py nfe_spike_ale_homolog --dry-run

HTTP homolog (cert A1 + IE no Hub):
  python manage.py nfe_spike_ale_homolog --mode http

RTC emit homolog 2026:
  python manage.py nfe_spike_ale_homolog --mode http --rtc-mode emit --issue-date 2026-09-06
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Tenant
from apps.master_data.models import Customer, Provider
from apps.nfe.exceptions import NfeValidationError
from apps.nfe.homolog_spike import (
    ALE_CNPJ,
    ALE_TENANT_SLUG,
    build_homolog_preflight,
    run_homolog_spike,
    run_smoke_e2e,
    write_spike_evidence,
)


class Command(BaseCommand):
    help = "Spike NF-e homolog SP — tenant ALE com preflight cert+IE."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default=ALE_TENANT_SLUG)
        parser.add_argument("--cnpj", default=ALE_CNPJ)
        parser.add_argument("--mode", choices=("stub", "http"), default="http")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--series", type=int, default=1)
        parser.add_argument("--valor-cents", type=int, default=1500)
        parser.add_argument("--ncm", default="21069090")
        parser.add_argument("--rtc-mode", default="", help="shadow|emit (opcional)")
        parser.add_argument("--issue-date", default="", help="YYYY-MM-DD (RTC 2026)")
        parser.add_argument(
            "--out",
            default=".storage/nfe_spike_ale_evidence.json",
        )
        parser.add_argument(
            "--preflight-only",
            action="store_true",
            help="Só checklist cert+IE+gate, sem emitir",
        )
        parser.add_argument(
            "--smoke-e2e",
            action="store_true",
            help="Pipeline stub: emit + XML/DANFE + compare estrutural",
        )
        parser.add_argument(
            "--tp-amb",
            choices=("1", "2"),
            default="2",
            help="1=produção 2=homolog (smoke/produção real exige cert+IE)",
        )

    def handle(self, *args, **options):
        slug = options["tenant"]
        cnpj = "".join(ch for ch in options["cnpj"] if ch.isdigit())
        mode = options["mode"]
        dry_run = bool(options["dry_run"])

        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant {slug} não encontrado — provisione ALE no lab.") from exc

        provider = (
            Provider.objects.filter(tenant=tenant, document=cnpj, is_active=True).first()
            or Provider.objects.filter(tenant=tenant, document=cnpj).first()
        )
        if provider is None:
            raise CommandError(f"Provider {cnpj} ausente no tenant {slug}")

        issue_date = None
        if options["issue_date"]:
            issue_date = date.fromisoformat(options["issue_date"])

        rtc_mode = (options["rtc_mode"] or "").strip() or None
        preflight = build_homolog_preflight(
            tenant=tenant,
            provider=provider,
            http_mode=mode,
            rtc_mode=rtc_mode,
            issue_date=issue_date,
        )
        self.stdout.write(f"preflight ok={preflight['ok']} blockers={preflight['blockers']}")

        if options["preflight_only"]:
            out = Path(options["out"])
            out.write_text(
                __import__("json").dumps(preflight, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(f"preflight saved → {out.resolve()}")
            return

        tp_amb = str(options["tp_amb"])[:1]

        customer = (
            Customer.objects.filter(tenant=tenant, is_active=True).order_by("created_at").first()
        )
        if customer is None:
            raise CommandError("Cadastre um Customer no tenant antes do spike.")

        if options["smoke_e2e"]:
            smoke_mode = "stub" if tp_amb == "2" else mode
            if tp_amb == "1" and mode == "http" and not preflight["ok"]:
                raise CommandError(
                    f"Smoke produção bloqueado: {preflight['blockers']}"
                )
            smoke = run_smoke_e2e(
                tenant=tenant,
                provider=provider,
                customer=customer,
                mode=smoke_mode,
                tp_amb=tp_amb,
                dry_run=dry_run,
                valor_cents=int(options["valor_cents"]),
            )
            out = Path(options["out"])
            out.write_text(
                __import__("json").dumps(smoke, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            self.stdout.write(f"smoke_ok={smoke['smoke_ok']} tpAmb={tp_amb}")
            self.stdout.write(f"evidence={out.resolve()}")
            if smoke["smoke_ok"]:
                self.stdout.write(self.style.SUCCESS("SMOKE E2E PASS"))
            else:
                raise CommandError(f"Smoke E2E falhou: {smoke}")
            return

        try:
            inv, _pf = run_homolog_spike(
                tenant=tenant,
                provider=provider,
                customer=customer,
                mode=mode,
                dry_run=dry_run,
                series=int(options["series"]),
                valor_cents=int(options["valor_cents"]),
                ncm=options["ncm"],
                rtc_mode=rtc_mode,
                issue_date=issue_date,
                tp_amb=tp_amb,
            )
        except NfeValidationError as exc:
            raise CommandError(str(exc)) from exc

        evidence = write_spike_evidence(
            inv=inv,
            provider=provider,
            preflight=preflight,
            mode=mode,
            dry_run=dry_run,
            out=Path(options["out"]),
            tenant_slug=slug,
        )
        self.stdout.write(self.style.SUCCESS(f"status={inv.status} key={inv.access_key or '—'}"))
        self.stdout.write(f"evidence={Path(options['out']).resolve()}")
        if evidence.get("g_spike_candidate"):
            self.stdout.write(self.style.SUCCESS("G-SPIKE CANDIDATE (HTTP authorized)"))
