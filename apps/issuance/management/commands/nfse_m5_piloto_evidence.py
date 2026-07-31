"""Pacote evidência M5 — piloto / KPIs / ops cert (Plano §3.1 + §15)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.issuance.metrics import compute_nfse_piloto_kpis
from apps.issuance.models import NfArtifact


class Command(BaseCommand):
    help = "Consolida evidência M5 (KPIs, beat cert, flags SEFIN) para parecer piloto."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=60)
        parser.add_argument(
            "--tenant",
            default="agendador-qa",
            help="Slug do tenant piloto (default agendador-qa).",
        )
        parser.add_argument("--out", default=".storage/sefin_m5_piloto_evidence.json")

    def handle(self, *args, **options):
        beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        cert_beat = beat.get("accounts-scan-expiring-certificates")
        since = timezone.now() - timedelta(days=int(options["days"]))
        tenant_slug = (options["tenant"] or "").strip()
        tenant = Tenant.objects.filter(slug=tenant_slug).first() if tenant_slug else None
        tenant_kpis = None
        artifact_count = None
        if tenant is not None:
            tenant_kpis = compute_nfse_piloto_kpis(since=since, tenant_id=tenant.id)
            artifact_count = NfArtifact.objects.filter(tenant_id=tenant.id).count()

        report = {
            "generated_at": timezone.now().isoformat(),
            "m5_criteria": {
                "piloto_prestador_ou_10_homolog": (
                    "Usar smoke_sefin_hub_emit / evidências .storage/sefin_m3_* "
                    "e sefin_m4_*; prestador EXEQ 37229907000137 em prod controlada."
                ),
                "alerta_cert": bool(cert_beat),
                "runbook": "Docs/Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md §12.1",
                "qa_ex": "Docs/Exeq_Hub_QA_Roteiro_NFSe_EX_Criticos.md",
                "po_aprovacao": "Docs/Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md §11.2",
                "convenio": "manage.py nfse_check_convenio --ibge 3504107 --environment production",
                "kpis": "manage.py nfse_piloto_kpis",
            },
            "settings": {
                "NFSE_DEFAULT_PROVIDER": getattr(settings, "NFSE_DEFAULT_PROVIDER", ""),
                "SEFIN_HTTP_MODE": getattr(settings, "SEFIN_HTTP_MODE", ""),
                "SEFIN_ENVIRONMENT": getattr(settings, "SEFIN_ENVIRONMENT", ""),
                "NFSE_CONVENIO_MODE": getattr(settings, "NFSE_CONVENIO_MODE", ""),
                "cert_beat_task": (cert_beat or {}).get("task"),
                "cert_beat_schedule_seconds": (cert_beat or {}).get("schedule"),
            },
            "piloto_tenant": {
                "slug": tenant_slug,
                "found": tenant is not None,
                "tenant_id": str(tenant.id) if tenant else None,
                "artifact_count": artifact_count,
                "kpis": tenant_kpis,
            },
            "kpis_global": compute_nfse_piloto_kpis(since=since),
            "po_checklist": {
                "C1_emit_cancel_xml_pdf": "Admin: ≥1 authorized→cancelled com XML+PDF no tenant piloto",
                "C2_cert_beat": "cert_beat_task presente + Celery beat rodando",
                "C3_runbook": "Ops leu Plano §12.1",
                "C4_kpis": "kpis do tenant piloto no JSON + nfse_piloto_kpis",
                "C5_g_sec_p0_host": "nfse_g_sec_p0_check verde no HOST piloto (DEBUG=False)",
                "C6_convenio": "Atibaia 3504107 apto em production",
            },
            "evidence_hints": [
                ".storage/sefin_m3_hub_e2e_evidence.json",
                ".storage/sefin_m4_hub_cancel70_evidence.json",
                ".storage/m1_aceite/cobertura_m1.json",
                ".storage/sefin_g_sec_p0_check.json",
                ".storage/sefin_m5_kpis.json",
            ],
        }
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"M5 evidência: {out}"))
        if not cert_beat:
            self.stdout.write(self.style.WARNING("Beat de certificado ausente nas settings"))
        if tenant is None and tenant_slug:
            self.stdout.write(self.style.WARNING(f"Tenant slug não encontrado: {tenant_slug}"))
