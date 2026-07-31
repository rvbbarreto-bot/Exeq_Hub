"""Spike M2 — handshake mTLS SEFIN + POST evidência (ADR-NFSE-001).

Uso:
  python manage.py spike_sefin_mtls --tenant agendador-qa --cnpj 37229907000137
  python manage.py spike_sefin_mtls --tenant agendador-qa --cnpj 37229907000137 --post-dps path/dps.xml
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.certificates import load_primary_pfx_material
from apps.accounts.models import Tenant
from integrations.nfse.sefin_client import SefinHttpClient, SefinHttpError


class Command(BaseCommand):
    help = "M2: prova mTLS SEFIN (handshake) e opcionalmente POST /nfse com DPS."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug do tenant")
        parser.add_argument("--cnpj", required=True, help="CNPJ do prestador (cert primary)")
        parser.add_argument(
            "--environment",
            default="homolog",
            help="homolog | production (default homolog)",
        )
        parser.add_argument(
            "--post-dps",
            default="",
            help="caminho de XML DPS assinada para POST /nfse (opcional)",
        )
        parser.add_argument(
            "--out",
            default="",
            help="arquivo JSON de evidência (default: .storage/sefin_m2_evidence.json)",
        )

    def handle(self, *args, **options):
        slug = options["tenant"]
        cnpj = "".join(ch for ch in options["cnpj"] if ch.isdigit())
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {slug}") from exc

        try:
            pfx_bytes, password = load_primary_pfx_material(
                tenant=tenant, cnpj=cnpj, purpose="nfse"
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Certificado A1 indisponível: {exc}") from exc

        client = SefinHttpClient(
            pfx_bytes=pfx_bytes,
            pfx_password=password,
            environment=options["environment"],
        )
        evidence: dict = {
            "tenant": slug,
            "cnpj": cnpj,
            "environment": options["environment"],
            "base_url": client.base_url,
        }
        try:
            evidence["handshake"] = client.handshake()
            self.stdout.write(self.style.SUCCESS("Handshake mTLS OK"))
            self.stdout.write(json.dumps(evidence["handshake"], ensure_ascii=False))

            dps_path = (options.get("post_dps") or "").strip()
            if dps_path:
                xml = Path(dps_path).read_bytes()
                try:
                    resp = client.emitir_dps(dps_xml=xml)
                    evidence["post_nfse"] = {
                        "http_status": resp.status_code,
                        "data": resp.data,
                        "has_xml": bool(resp.xml_bytes),
                    }
                    self.stdout.write(
                        self.style.SUCCESS(f"POST /nfse HTTP {resp.status_code}")
                    )
                except SefinHttpError as exc:
                    evidence["post_nfse"] = {
                        "error": str(exc),
                        "http_status": exc.status_code,
                        "raw": exc.raw,
                    }
                    self.stdout.write(self.style.WARNING(f"POST /nfse: {exc}"))
            else:
                evidence["post_nfse"] = {
                    "skipped": True,
                    "reason": "informe --post-dps com XML DPS assinada para tentar autorização",
                }
                self.stdout.write(
                    "POST /nfse omitido (sem --post-dps). Handshake basta para evidência M2 parcial."
                )
        finally:
            client.close()

        out = Path(options["out"] or ".storage/sefin_m2_evidence.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Evidência salva em {out}"))
