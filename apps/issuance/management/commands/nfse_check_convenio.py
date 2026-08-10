"""Consulta aptidão municipal (RF-01) — diagnóstico ops/piloto."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from integrations.nfse.convenio import get_convenio_status, normalize_sefin_environment


class Command(BaseCommand):
    help = (
        "Consulta se o município IBGE está apto ao Ambiente Nacional. "
        "Em NFSE_CONVENIO_MODE=http, use --pfx ou --tenant/--cnpj (ADN exige mTLS)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--ibge", required=True, help="Código IBGE (7 dígitos).")
        parser.add_argument(
            "--environment",
            default="",
            help="homolog | production (default: SEFIN_ENVIRONMENT).",
        )
        parser.add_argument("--refresh", action="store_true", help="Ignora cache.")
        parser.add_argument("--out", default="", help="Salva JSON de evidência.")
        parser.add_argument(
            "--pfx",
            default="",
            help="Caminho PFX A1 para mTLS ADN (modo http).",
        )
        parser.add_argument("--pfx-password", default="", help="Senha do PFX.")
        parser.add_argument(
            "--tenant",
            default="",
            help="Slug do tenant para carregar A1 (alternativa a --pfx).",
        )
        parser.add_argument(
            "--cnpj",
            default="",
            help="CNPJ do prestador (com --tenant).",
        )

    def handle(self, *args, **options):
        env = options["environment"] or None
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

        status = get_convenio_status(
            options["ibge"],
            environment=env,
            force_refresh=bool(options["refresh"]) or bool(pfx_bytes),
            pfx_bytes=pfx_bytes,
            pfx_password=pfx_password,
        )
        payload = {
            "ibge_code": status.ibge_code,
            "environment": status.environment or normalize_sefin_environment(env),
            "apto": status.aderente,
            "source": status.source,
            "raw": status.raw,
            "mtls": bool(pfx_bytes),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        if status.aderente:
            self.stdout.write(self.style.SUCCESS("APTO"))
        else:
            self.stdout.write(self.style.ERROR("NAO APTO (EX-PRE-01)"))
        out = (options["out"] or "").strip()
        if out:
            Path(out).write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Salvo: {out}"))
