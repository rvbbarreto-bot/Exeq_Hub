"""Consulta aptidão municipal (RF-01) — diagnóstico ops/piloto."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from integrations.nfse.convenio import get_convenio_status, normalize_sefin_environment


class Command(BaseCommand):
    help = "Consulta se o município IBGE está apto ao Ambiente Nacional no ambiente alvo."

    def add_arguments(self, parser):
        parser.add_argument("--ibge", required=True, help="Código IBGE (7 dígitos).")
        parser.add_argument(
            "--environment",
            default="",
            help="homolog | production (default: SEFIN_ENVIRONMENT).",
        )
        parser.add_argument("--refresh", action="store_true", help="Ignora cache.")
        parser.add_argument("--out", default="", help="Salva JSON de evidência.")

    def handle(self, *args, **options):
        env = options["environment"] or None
        status = get_convenio_status(
            options["ibge"],
            environment=env,
            force_refresh=bool(options["refresh"]),
        )
        payload = {
            "ibge_code": status.ibge_code,
            "environment": status.environment or normalize_sefin_environment(env),
            "apto": status.aderente,
            "source": status.source,
            "raw": status.raw,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        if status.aderente:
            self.stdout.write(self.style.SUCCESS("APTO"))
        else:
            self.stdout.write(self.style.ERROR("NAO APTO (EX-PRE-01)"))
        out = (options["out"] or "").strip()
        if out:
            from pathlib import Path

            Path(out).write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Salvo: {out}"))
