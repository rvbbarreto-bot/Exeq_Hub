"""Smoke RF-01 — convênio HTTP ADN multi-IBGE (cobertura municípios aderentes)."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from integrations.nfse.convenio import check_convenio_batch, normalize_sefin_environment


class Command(BaseCommand):
    help = (
        "Valida aptidão de vários IBGE via ADN (NFSE_CONVENIO_MODE=http + mTLS). "
        "Gera evidência JSON para ops de escala."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ibge-list",
            default="3504107",
            help="IBGE separados por vírgula (ex. 3504107,3550308).",
        )
        parser.add_argument(
            "--environment",
            default="",
            help="homolog | production (default: SEFIN_ENVIRONMENT).",
        )
        parser.add_argument("--tenant", default="", help="Slug tenant com A1 NFS-e.")
        parser.add_argument("--cnpj", default="", help="CNPJ prestador (com --tenant).")
        parser.add_argument("--pfx", default="", help="PFX A1 (alternativa a --tenant).")
        parser.add_argument("--pfx-password", default="")
        parser.add_argument(
            "--require-http-mode",
            action="store_true",
            help="Falha se NFSE_CONVENIO_MODE != http.",
        )
        parser.add_argument(
            "--out",
            default=".storage/sefin_convenio_http_smoke.json",
            help="Arquivo de evidência.",
        )

    def handle(self, *args, **options):
        mode = (getattr(settings, "NFSE_CONVENIO_MODE", "stub") or "stub").lower()
        if options["require_http_mode"] and mode != "http":
            raise CommandError(
                f"NFSE_CONVENIO_MODE={mode}; defina http no host para smoke ADN real."
            )

        pfx_bytes = None
        pfx_password = options["pfx_password"] or ""
        pfx_path = (options["pfx"] or "").strip()
        if pfx_path:
            path = Path(pfx_path)
            if not path.is_file():
                raise CommandError(f"PFX não encontrado: {pfx_path}")
            pfx_bytes = path.read_bytes()
        elif (options["tenant"] or "").strip():
            from apps.accounts.certificates import load_primary_pfx_material
            from apps.accounts.models import Tenant

            slug = options["tenant"].strip()
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is None:
                raise CommandError(f"Tenant não encontrado: {slug}")
            pfx_bytes, pfx_password = load_primary_pfx_material(
                tenant=tenant,
                cnpj=(options["cnpj"] or "").strip(),
                purpose="nfse",
            )
        elif mode == "http":
            raise CommandError(
                "Modo http exige mTLS: informe --tenant/--cnpj ou --pfx "
                "(ADN retorna 496 sem certificado)."
            )

        codes = [
            c.strip()
            for c in (options["ibge_list"] or "").split(",")
            if c.strip()
        ]
        if not codes:
            raise CommandError("--ibge-list vazio")

        env = options["environment"] or None
        results = check_convenio_batch(
            codes,
            environment=env,
            pfx_bytes=pfx_bytes,
            pfx_password=pfx_password,
            force_refresh=True,
        )
        rows = [
            {
                "ibge_code": s.ibge_code,
                "apto": s.aderente,
                "source": s.source,
                "environment": s.environment,
                "raw_http_status": (s.raw or {}).get("http_status"),
                "error": (s.raw or {}).get("error"),
            }
            for s in results
        ]
        aptos = sum(1 for r in rows if r["apto"])
        payload = {
            "nfse_convenio_mode": mode,
            "environment": normalize_sefin_environment(env),
            "mtls": bool(pfx_bytes),
            "total": len(rows),
            "aptos": aptos,
            "nao_aptos": len(rows) - aptos,
            "results": rows,
            "ops_hint": (
                "Para escala: NFSE_CONVENIO_MODE=http + A1 do prestador; "
                "stub só cobre semente NFSE_NATIONAL_IBGE_CODES."
            ),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Evidência: {out}"))
        if aptos == 0 and mode == "http":
            self.stdout.write(
                self.style.WARNING(
                    "Nenhum IBGE apto — confira ambiente, mTLS e adesão ADN."
                )
            )
        elif aptos:
            self.stdout.write(self.style.SUCCESS(f"APTOS: {aptos}/{len(rows)}"))
