"""Ops: checklist pré-G-EMIT (sem POST SEFAZ)."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Tenant
from apps.nfe.g_emit_checklist import build_g_emit_checklist


class Command(BaseCommand):
    help = (
        "Gera checklist JSON de prontidão G-EMIT (gate + env). "
        "Não consulta SEFAZ. exit 0 se dry-run ready; exit 2 se bloqueado."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug do tenant")
        parser.add_argument("--cnpj", default="", help="CNPJ emitente opcional")
        parser.add_argument("--provider-id", default="", dest="provider_id")
        parser.add_argument("--series", type=int, default=1)
        parser.add_argument("--tp-amb", default="", dest="tp_amb")
        parser.add_argument(
            "--out",
            default=".storage/nfe_g_emit_checklist.json",
            help="arquivo de saída",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="exige ready_for_http_emit (sem dry_run)",
        )

    def handle(self, *args, **options):
        try:
            tenant = Tenant.objects.get(slug=options["tenant"])
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {options['tenant']}") from exc

        payload = build_g_emit_checklist(
            tenant=tenant,
            provider_id=(options.get("provider_id") or "").strip() or None,
            cnpj=(options.get("cnpj") or "").strip() or None,
            series=int(options.get("series") or 1),
            tp_amb=(options.get("tp_amb") or "").strip() or None,
        )
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(
            f"ready_http={payload['ready_for_http_emit']} "
            f"ready_dry={payload['ready_for_http_dry_run']} "
            f"blockers={payload['blockers']}"
        )
        self.stdout.write(f"evidence={out.resolve()}")

        if options.get("strict"):
            if not payload["ready_for_http_emit"]:
                raise CommandError(
                    "checklist strict falhou: " + ",".join(payload["blockers"] or ["?"])
                )
        elif not payload["ready_for_http_dry_run"]:
            raise CommandError(
                "checklist bloqueado: " + ",".join(payload["blockers"] or ["?"])
            )
