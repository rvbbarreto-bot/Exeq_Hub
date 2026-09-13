"""Onboarding multi-CNPJ / multi-tenant NFS-e — idempotente."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.issuance.onboarding import onboard_nfse_tenant


class Command(BaseCommand):
    help = (
        "Provisiona tenant+usuário+prestador+serviço+perfil/regra fiscal "
        "(+A1 opcional) para emissão NFS-e Nacional. Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True)
        parser.add_argument("--cnpj", required=True)
        parser.add_argument("--legal-name", required=True)
        parser.add_argument("--user-email", required=True)
        parser.add_argument("--user-password", default="")
        parser.add_argument("--role", default="tenant_admin")
        parser.add_argument("--tax-regime", default="simples_nacional")
        parser.add_argument("--im", default="", help="Inscrição municipal do prestador")
        parser.add_argument("--ibge", default="3504107")
        parser.add_argument("--municipio-nome", default="Atibaia")
        parser.add_argument("--uf", default="SP")
        parser.add_argument("--service-code", default="170101")
        parser.add_argument("--service-description", default="Servico onboarding Hub SEFIN")
        parser.add_argument("--c-trib-nac", default="", help="cTribNac (default=service-code)")
        parser.add_argument("--fiscal-profile-name", default="SN-ONBOARD")
        parser.add_argument("--iss-rate", default="0.02")
        parser.add_argument("--simples-codigo", type=int, default=3)
        parser.add_argument("--valid-from", default="2024-01-01")
        parser.add_argument("--pfx", default="", help="Caminho do PFX A1")
        parser.add_argument("--pfx-password", default="")
        parser.add_argument("--cert-label", default="A1-onboard")
        parser.add_argument("--skip-cert", action="store_true")
        parser.add_argument("--out", default="", help="Salva JSON do resultado")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        pfx_bytes = None
        pfx_path = (options["pfx"] or "").strip()
        if pfx_path:
            path = Path(pfx_path)
            if not path.is_file():
                raise CommandError(f"PFX não encontrado: {pfx_path}")
            pfx_bytes = path.read_bytes()

        try:
            valid_from = date.fromisoformat(options["valid_from"])
            iss_rate = Decimal(str(options["iss_rate"]))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "dry_run": True,
                        "slug": options["slug"],
                        "cnpj": options["cnpj"],
                        "ibge": options["ibge"],
                        "service_code": options["service_code"],
                        "has_pfx": bool(pfx_bytes),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        try:
            result = onboard_nfse_tenant(
                slug=options["slug"],
                cnpj=options["cnpj"],
                legal_name=options["legal_name"],
                user_email=options["user_email"],
                user_password=options["user_password"] or "",
                role_code=options["role"],
                tax_regime=options["tax_regime"],
                municipal_registration=options["im"] or "",
                ibge_code=options["ibge"],
                municipio_nome=options["municipio_nome"],
                uf=options["uf"],
                service_code=options["service_code"],
                service_description=options["service_description"],
                c_trib_nac=options["c_trib_nac"] or "",
                fiscal_profile_name=options["fiscal_profile_name"],
                iss_rate=iss_rate,
                simples_codigo_tributacao=int(options["simples_codigo"]),
                valid_from=valid_from,
                pfx_bytes=pfx_bytes,
                pfx_password=options["pfx_password"] or "",
                cert_label=options["cert_label"],
                skip_cert=bool(options["skip_cert"]),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = result.as_dict()
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.stdout.write(text)
        self.stdout.write(self.style.SUCCESS(f"Onboard OK tenant={result.tenant_slug}"))
        out = (options["out"] or "").strip()
        if out:
            Path(out).write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Salvo: {out}"))
