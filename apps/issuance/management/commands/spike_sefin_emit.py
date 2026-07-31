"""Spike M3 — monta DPS + XMLDSig + POST /nfse em homologação SEFIN.

Uso típico (cert no tenant agendador-qa, prestador CNPJ do A1):
  python manage.py spike_sefin_emit --tenant-cert agendador-qa --cnpj 37229907000137 ^
      --ibge 3504107 --cTribNac 010101 --valor 15.00 --tomador-cpf 52998224725
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.certificates import load_primary_pfx_material
from apps.accounts.models import Tenant
from integrations.nfse.dps import build_dps_xml_from_dict
from integrations.nfse.sefin_client import SefinHttpClient, SefinHttpError
from integrations.nfse.xmldsig import sign_dps_xml, verify_dps_has_signature


class Command(BaseCommand):
    help = "M3: assina DPS e tenta POST /SefinNacional/nfse em homolog."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-cert", required=True, help="slug do tenant do A1")
        parser.add_argument("--cnpj", required=True, help="CNPJ prestador (= CNPJ do A1)")
        parser.add_argument("--ibge", default="3504107")
        parser.add_argument("--cTribNac", default="010101")
        parser.add_argument("--valor", default="15.00")
        parser.add_argument("--serie", default="1")
        parser.add_argument("--n-dps", default="", help="número DPS (default: timestamp)")
        parser.add_argument("--tomador-cpf", default="")
        parser.add_argument("--tomador-cnpj", default="")
        parser.add_argument("--tomador-nome", default="TOMADOR SPIKE EXEQ")
        parser.add_argument("--descricao", default="Servico spike SEFIN EXEQ Hub")
        parser.add_argument("--cep", default="01001000", help="CEP do tomador (deve bater com --ibge)")
        parser.add_argument("--environment", default="homolog")
        parser.add_argument("--out", default=".storage/sefin_m3_emit_evidence.json")
        parser.add_argument(
            "--save-xml",
            default=".storage/sefin_m3_dps_signed.xml",
            help="grava XML assinado",
        )

    def handle(self, *args, **options):
        slug = options["tenant_cert"]
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

        n_dps = options["n_dps"] or str(int(datetime.now().timestamp()))[-12:]
        ibge = "".join(ch for ch in options["ibge"] if ch.isdigit()).zfill(7)
        valor = f"{Decimal(str(options['valor'])).quantize(Decimal('0.01'))}"
        now = datetime.now(ZoneInfo("America/Sao_Paulo"))

        from integrations.nfse.dps import build_dps_id

        dps_id = build_dps_id(
            c_loc_emi=ibge,
            prestador_doc=cnpj,
            is_cpf=False,
            serie=options["serie"],
            n_dps=n_dps,
        )
        tomador_cpf = "".join(ch for ch in (options.get("tomador_cpf") or "") if ch.isdigit())
        tomador_cnpj = "".join(ch for ch in (options.get("tomador_cnpj") or "") if ch.isdigit())
        if not tomador_cpf and not tomador_cnpj:
            tomador_cpf = "52998224725"
            self.stdout.write(
                self.style.WARNING(
                    "Usando CPF lab padrão; se vier E0207, informe --tomador-cpf/--tomador-cnpj real (RFB)."
                )
            )
        toma: dict = {"xNome": options["tomador_nome"]}
        if tomador_cpf:
            toma["CPF"] = tomador_cpf
        else:
            toma["CNPJ"] = tomador_cnpj
        cep = "".join(ch for ch in options["cep"] if ch.isdigit()).zfill(8)[-8:]
        toma["end"] = {
            "endNac": {"cMun": ibge, "CEP": cep},
            "xLgr": "Rua Spike",
            "nro": "1",
            "xBairro": "Centro",
        }
        payload = {
            "infDPS": {
                "Id": dps_id,
                "tpAmb": 2 if options["environment"].lower().startswith("homolog") else 1,
                "dhEmi": now.isoformat(timespec="seconds"),
                "verAplic": "EXEQHUB_1.0",
                "serie": str(int(options["serie"])),
                "nDPS": str(int(n_dps)),
                "dCompet": date.today().isoformat(),
                "tpEmit": 1,
                "cLocEmi": ibge,
                "prest": {
                    "CNPJ": cnpj,
                    "regTrib": {"opSimpNac": 3, "regApTribSN": 1, "regEspTrib": 0},
                },
                "toma": toma,
                "serv": {
                    "locPrest": {"cLocPrestacao": ibge},
                    "cServ": {
                        "cTribNac": "".join(
                            ch for ch in options["cTribNac"] if ch.isdigit()
                        ).zfill(6)[:6],
                        "xDescServ": options["descricao"],
                    },
                },
                "valores": {
                    "vServPrest": {"vServ": valor},
                    "trib": {
                        "tribMun": {"tribISSQN": 1, "tpRetISSQN": 1},
                        "totTrib": {"pTotTribSN": "6.00"},
                    },
                },
            }
        }

        unsigned = build_dps_xml_from_dict(payload)
        signed = sign_dps_xml(dps_xml=unsigned, pfx_bytes=pfx_bytes, password=password)
        if not verify_dps_has_signature(signed):
            raise CommandError("XMLDSig falhou — Signature ausente")

        xml_path = Path(options["save_xml"])
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_bytes(signed)
        self.stdout.write(self.style.SUCCESS(f"DPS assinada: {xml_path}"))

        client = SefinHttpClient(
            pfx_bytes=pfx_bytes,
            pfx_password=password,
            environment=options["environment"],
        )
        evidence = {
            "tenant_cert": slug,
            "cnpj": cnpj,
            "dps_id": dps_id,
            "n_dps": n_dps,
            "base_url": client.base_url,
            "xml_path": str(xml_path),
        }
        try:
            evidence["handshake"] = client.handshake()
            resp = client.emitir_dps(dps_xml=signed)
            evidence["post_nfse"] = {
                "http_status": resp.status_code,
                "data": resp.data,
                "has_xml": bool(resp.xml_bytes),
            }
            if resp.xml_bytes:
                Path(".storage/sefin_m3_nfse_autorizada.xml").write_bytes(resp.xml_bytes)
            self.stdout.write(
                self.style.SUCCESS(f"POST /nfse HTTP {resp.status_code}")
            )
            self.stdout.write(json.dumps(resp.data, ensure_ascii=False, indent=2)[:2000])
        except SefinHttpError as exc:
            evidence["post_nfse"] = {
                "error": str(exc),
                "http_status": exc.status_code,
                "raw": exc.raw,
            }
            self.stdout.write(self.style.WARNING(f"POST /nfse: {exc}"))
            if exc.raw:
                self.stdout.write(json.dumps(exc.raw, ensure_ascii=False, indent=2)[:2000])
        finally:
            client.close()

        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Evidência: {out}"))
