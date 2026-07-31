"""M4 — cancela NFS-e Nacional via pedRegEvento e101101.

Uso:
  python manage.py spike_sefin_cancel --tenant-cert agendador-qa --cnpj 37229907000137 ^
      --chave 35041072237229907000137000000000006826077669419404 ^
      --environment production --motivo "Cancelamento lab EXEQ Hub NFS-e 68"
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.certificates import load_primary_pfx_material
from apps.accounts.models import Tenant
from integrations.nfse.evento import build_cancel_ped_reg_evento_xml
from integrations.nfse.sefin_client import SefinHttpClient, SefinHttpError
from integrations.nfse.xmldsig import sign_ped_reg_evento_xml, verify_dps_has_signature


class Command(BaseCommand):
    help = "M4: assina pedRegEvento de cancelamento e POST /nfse/{chave}/eventos."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-cert", required=True)
        parser.add_argument("--cnpj", required=True)
        parser.add_argument("--chave", required=True, help="chaveAcesso 50 dígitos")
        parser.add_argument(
            "--motivo",
            default="Cancelamento laboratorial EXEQ Hub apos spike de emissao",
        )
        parser.add_argument("--c-motivo", type=int, default=1)
        parser.add_argument("--environment", default="production")
        parser.add_argument("--out", default=".storage/sefin_m4_cancel_evidence.json")
        parser.add_argument(
            "--save-xml",
            default=".storage/sefin_m4_ped_reg_evento_signed.xml",
        )

    def handle(self, *args, **options):
        slug = options["tenant_cert"]
        cnpj = "".join(ch for ch in options["cnpj"] if ch.isdigit())
        chave = "".join(ch for ch in options["chave"] if ch.isdigit())
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

        env = options["environment"]
        tp_amb = 1 if not str(env).lower().startswith("homolog") else 2
        unsigned = build_cancel_ped_reg_evento_xml(
            chave_acesso=chave,
            autor_cnpj=cnpj,
            x_motivo=options["motivo"],
            c_motivo=options["c_motivo"],
            tp_amb=tp_amb,
        )
        signed = sign_ped_reg_evento_xml(
            evento_xml=unsigned, pfx_bytes=pfx_bytes, password=password
        )
        if not verify_dps_has_signature(signed):
            raise CommandError("XMLDSig falhou — Signature ausente no pedRegEvento")

        xml_path = Path(options["save_xml"])
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_bytes(signed)
        self.stdout.write(self.style.SUCCESS(f"Evento assinado: {xml_path}"))

        client = SefinHttpClient(
            pfx_bytes=pfx_bytes,
            pfx_password=password,
            environment=env,
        )
        evidence = {
            "tenant_cert": slug,
            "cnpj": cnpj,
            "chave": chave,
            "base_url": client.base_url,
            "xml_path": str(xml_path),
            "tp_amb": tp_amb,
        }
        try:
            resp = client.registrar_evento(chave_acesso=chave, evento_xml=signed)
            evidence["post_evento"] = {
                "http_status": resp.status_code,
                "data": resp.data,
            }
            self.stdout.write(
                self.style.SUCCESS(f"POST /eventos HTTP {resp.status_code}")
            )
            self.stdout.write(json.dumps(resp.data, ensure_ascii=False, indent=2)[:2000])
        except SefinHttpError as exc:
            evidence["post_evento"] = {
                "error": str(exc),
                "http_status": exc.status_code,
                "raw": exc.raw,
            }
            self.stdout.write(self.style.WARNING(f"POST /eventos: {exc}"))
            if exc.raw:
                self.stdout.write(json.dumps(exc.raw, ensure_ascii=False, indent=2)[:2000])
        finally:
            client.close()

        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Evidência: {out}"))
