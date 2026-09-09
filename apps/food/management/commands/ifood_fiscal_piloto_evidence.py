"""Pacote evidência piloto iFood fiscal — parecer go-live."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.food.fiscal.metrics import compute_ifood_fiscal_piloto_kpis
from apps.food.fiscal.piloto_check import run_ifood_fiscal_piloto_checks


class Command(BaseCommand):
    help = "Consolida evidência piloto iFood fiscal (checklist + KPIs + beat) para PO/Ops."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Slug tenant piloto")
        parser.add_argument("--days", type=int, default=7, help="Janela KPIs")
        parser.add_argument(
            "--out",
            default=".storage/ifood_fiscal_piloto_evidence.json",
        )

    def handle(self, *args, **options):
        slug = (options["tenant"] or "").strip()
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            raise CommandError(f"Tenant não encontrado: {slug}")

        check = run_ifood_fiscal_piloto_checks(tenant=tenant, strict_prod=False)
        beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}

        report = {
            "generated_at": timezone.now().isoformat(),
            "epic": "iFood fiscal Opção B — piloto produção",
            "reference": "Docs/DISCOVERY_IFOOD_FISCAL_B.md §6 DoD",
            "piloto_tenant": {
                "slug": slug,
                "id": str(tenant.id),
                "legal_name": tenant.legal_name,
            },
            "premissa": "1 loja SP · ~200 pedidos/dia · emissão supervisionada · polling iFood",
            "checklist": check,
            "kpis": compute_ifood_fiscal_piloto_kpis(tenant_id=tenant.id),
            "celery_beat": {
                k: {"task": v.get("task"), "schedule": v.get("schedule")}
                for k, v in beat.items()
                if (v.get("task") or "").startswith(("food.", "nfce."))
            },
            "settings_snapshot": {
                "NFCE_ENABLED": getattr(settings, "NFCE_ENABLED", False),
                "NFCE_HTTP_MODE": getattr(settings, "NFCE_HTTP_MODE", ""),
                "NFCE_DEFAULT_TP_AMB": getattr(settings, "NFCE_DEFAULT_TP_AMB", ""),
                "MARKETPLACE_HTTP_MODE": getattr(settings, "MARKETPLACE_HTTP_MODE", ""),
                "FOOD_MARKETPLACE_SYNC_INTERVAL_SECONDS": getattr(
                    settings, "FOOD_MARKETPLACE_SYNC_INTERVAL_SECONDS", None
                ),
                "FOOD_FISCAL_RECONCILE_STALE_SECONDS": getattr(
                    settings, "FOOD_FISCAL_RECONCILE_STALE_SECONDS", None
                ),
            },
            "po_checklist": {
                "C1_check_verde": "manage.py ifood_fiscal_piloto_check --tenant <slug> --strict-prod",
                "C2_beat_worker": "celery worker + beat rodando no host",
                "C3_de_para": "100% SKUs do cardápio piloto mapeados",
                "C4_smoke_emit": "≥1 pedido iFood → AUTHORIZED com NFC-e vinculada",
                "C5_logs": "exeq.food.fiscal sem secrets (EX-SEC-04)",
                "C6_runbook_cancel": "Cancel iFood logístico não cancela NFC-e (PO-3 manual)",
            },
            "commands": {
                "check": f"manage.py ifood_fiscal_piloto_check --tenant {slug} --strict-prod",
                "sync": "celery beat food.sync_marketplace_orders (120s default)",
                "reconcile": "celery beat food.reconcile_ifood_fiscal",
                "hub_fila": "/hub/food/pedidos/ifood-fiscal/",
            },
        }

        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Evidência piloto iFood fiscal: {out}"))
        if check.get("ready_for_pilot"):
            self.stdout.write(self.style.SUCCESS("Checklist obrigatório: OK (modo lab)."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Pendências: {check['summary']['fail_required']} obrigatória(s)"
                )
            )
