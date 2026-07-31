"""Imprime KPIs do piloto NFS-e (M5 / Plano §15)."""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.issuance.metrics import compute_nfse_piloto_kpis


class Command(BaseCommand):
    help = "Agrega KPIs mínimos do piloto NFS-e (authorization/rejection/happy-path/certs)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Janela relativa em dias (default 30).",
        )
        parser.add_argument("--since", type=str, default="", help="ISO datetime início.")
        parser.add_argument("--until", type=str, default="", help="ISO datetime fim.")
        parser.add_argument("--tenant-id", type=str, default="", help="Filtra por tenant UUID.")
        parser.add_argument(
            "--out",
            type=str,
            default="",
            help="Salva JSON em arquivo (ex. .storage/sefin_m5_kpis.json).",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        since = parse_datetime(options["since"]) if options["since"] else None
        until = parse_datetime(options["until"]) if options["until"] else None
        if since is None:
            since = now - timedelta(days=int(options["days"]))
        if until is None:
            until = now
        if since and timezone.is_naive(since):
            since = timezone.make_aware(since, timezone.get_current_timezone())
        if until and timezone.is_naive(until):
            until = timezone.make_aware(until, timezone.get_current_timezone())

        tenant_id = options["tenant_id"] or None
        report = compute_nfse_piloto_kpis(
            since=since, until=until, tenant_id=tenant_id
        )
        text = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        out = (options["out"] or "").strip()
        if out:
            from pathlib import Path

            Path(out).write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Salvo: {out}"))
