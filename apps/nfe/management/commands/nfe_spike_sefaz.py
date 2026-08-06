"""I7 — spike SEFAZ NF-e auditável (stub/dry-run sem rede; HTTP opcional).

Uso lab (sem POST):
  python manage.py nfe_spike_sefaz --tenant acme --cnpj 37229907000137 --mode stub

Monta+assina sem SEFAZ:
  python manage.py nfe_spike_sefaz --tenant acme --cnpj 37229907000137 --mode http --dry-run

HTTP homolog (requer cert A1 + IE; marca G-SPIKE na evidência se cStat 100):
  python manage.py nfe_spike_sefaz --tenant acme --cnpj 37229907000137 --mode http
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from apps.accounts.models import Tenant
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.exceptions import NfeDisabledError, NfeValidationError
from apps.nfe.models import NfeInvoice
from apps.nfe.services import (
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
)


class Command(BaseCommand):
    help = (
        "Spike NF-e SEFAZ-SP: emite 1 nota no Tenant (stub|http|dry-run). "
        "Saída JSON: status, cStat, chave, protocolo — sem secrets/PFX. "
        "Homolog authorized (cStat 100) → evidência g_spike_candidate=true "
        "(ops marca G-NFE-SPIKE no ticket). "
        "Default não habilita NFE_ENABLED em prod multi-tenant."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug do tenant")
        parser.add_argument("--cnpj", required=True, help="CNPJ emitente (= Provider / A1)")
        parser.add_argument(
            "--mode",
            choices=("stub", "http"),
            default="stub",
            help="NFE_HTTP_MODE local ao spike",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="com --mode http: assina XML e NÃO faz POST SEFAZ",
        )
        parser.add_argument("--series", type=int, default=1)
        parser.add_argument("--valor-cents", type=int, default=1500)
        parser.add_argument("--ncm", default="21069090")
        parser.add_argument(
            "--out",
            default=".storage/nfe_spike_evidence.json",
            help="arquivo de evidência auditável",
        )

    def handle(self, *args, **options):
        slug = options["tenant"]
        cnpj = "".join(ch for ch in options["cnpj"] if ch.isdigit())
        mode = options["mode"]
        dry_run = bool(options["dry_run"])
        if mode == "stub" and dry_run:
            self.stdout.write(self.style.WARNING("--dry-run ignorado em mode=stub"))

        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {slug}") from exc

        provider = (
            Provider.objects.filter(tenant=tenant, document=cnpj, is_active=True).first()
            or Provider.objects.filter(tenant=tenant, document=cnpj).first()
        )
        if provider is None:
            raise CommandError(
                f"Provider CNPJ {cnpj} inexistente no tenant {slug}. "
                "Cadastre o emitente (mesmo da NFS-e) antes do spike."
            )

        customer = (
            Customer.objects.filter(tenant=tenant, is_active=True)
            .order_by("created_at")
            .first()
        )
        if customer is None:
            customer = Customer.objects.create(
                tenant=tenant,
                document="12345678909",
                document_type=Customer.DocumentType.CPF,
                name="CLIENTE SPIKE NFE LAB",
                address={
                    "logradouro": "Av Spike",
                    "numero": "1",
                    "bairro": "Centro",
                    "municipio": "Atibaia",
                    "uf": "SP",
                    "cep": "12940000",
                    "codigo_ibge": "3504107",
                },
            )

        product_code = f"SPIKE-{uuid.uuid4().hex[:6].upper()}"
        idem = f"nfe-spike-{uuid.uuid4().hex[:12]}"
        overrides = {
            "NFE_ENABLED": True,
            "NFE_HTTP_MODE": mode,
            "NFE_HTTP_DRY_RUN": dry_run if mode == "http" else False,
            "NFE_DEFAULT_TP_AMB": "2",
        }

        with override_settings(**overrides):
            product = create_product(
                tenant=tenant,
                code=product_code,
                description="Item spike NF-e U3",
                ncm=options["ncm"],
                unit_price_cents=int(options["valor_cents"]),
                csosn="102",
            )
            inv = create_draft(
                tenant=tenant,
                provider=provider,
                customer=customer,
                idempotency_key=idem,
                series=int(options["series"]),
                nature_operation="VENDA SPIKE",
                actor="nfe_spike_sefaz",
            )
            if inv.issue_date is None:
                inv.issue_date = date.today()
                inv.save(update_fields=["issue_date", "updated_at"])
            replace_items(
                inv,
                items=[{"product_id": str(product.id), "quantity": "1"}],
            )
            inv.refresh_from_db()
            try:
                inv = emit_invoice(inv, actor="nfe_spike_sefaz")
            except (NfeValidationError, NfeDisabledError) as exc:
                raise CommandError(f"emit/validate: {exc}") from exc

        inv.refresh_from_db()
        events = list(
            inv.events.order_by("-occurred_at")[:5].values(
                "from_status", "to_status", "actor", "metadata", "occurred_at"
            )
        )
        # Normaliza metadata para JSON (sem body enormes / sem secrets)
        sanitized_events = []
        for ev in events:
            meta = ev.get("metadata") or {}
            raw = meta.get("raw") if isinstance(meta, dict) else None
            c_stat = ""
            x_motivo = ""
            if isinstance(raw, dict):
                c_stat = str(raw.get("cStat") or "")
                x_motivo = str(raw.get("xMotivo") or "")[:200]
            sanitized_events.append(
                {
                    "from": ev["from_status"],
                    "to": ev["to_status"],
                    "actor": ev["actor"],
                    "cStat": c_stat,
                    "xMotivo": x_motivo,
                    "at": ev["occurred_at"].isoformat()
                    if hasattr(ev["occurred_at"], "isoformat")
                    else str(ev["occurred_at"]),
                }
            )

        last_raw = {}
        if events:
            m0 = events[0].get("metadata") or {}
            if isinstance(m0, dict) and isinstance(m0.get("raw"), dict):
                last_raw = {
                    k: v
                    for k, v in m0["raw"].items()
                    if k
                    in {
                        "mode",
                        "stage",
                        "cStat",
                        "xMotivo",
                        "nProt",
                        "chNFe",
                        "http",
                        "lote_cStat",
                        "nRec",
                    }
                }

        c_stat = str(last_raw.get("cStat") or inv.rejection_code or "")
        g_spike = (
            mode == "http"
            and not dry_run
            and inv.status == NfeInvoice.Status.AUTHORIZED
            and c_stat in {"100", "150", ""}
        )
        # stub authorized without cStat still valid lab evidence, not G-SPIKE
        if mode == "stub":
            g_spike = False

        evidence = {
            "ticket": "I7",
            "gate": "G-NFE-SPIKE",
            "g_spike_candidate": g_spike,
            "note": (
                "Se g_spike_candidate=true, ops atualiza Docs/Exeq_Hub_NFe_U3_Tickets_I1_I8.md "
                "e ADR com evidência de homolog (cStat 100)."
                if g_spike
                else "Lab stub/dry-run ou falha — G-SPIKE NÃO marcado automaticamente."
            ),
            "tenant": slug,
            "cnpj": cnpj,
            "mode": mode,
            "dry_run": dry_run,
            "invoice_id": str(inv.id),
            "status": inv.status,
            "series": inv.series,
            "number": inv.number,
            "access_key": inv.access_key or "",
            "protocol": inv.protocol or "",
            "rejection_code": inv.rejection_code or "",
            "rejection_message": (inv.rejection_message or "")[:300],
            "cStat": c_stat,
            "sefaz_raw_safe": last_raw,
            "events": sanitized_events,
            "nfe_enabled_prod_default": False,
        }

        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"status={inv.status} cStat={c_stat or '—'}"))
        self.stdout.write(f"invoice={inv.id} key={inv.access_key or '—'} prot={inv.protocol or '—'}")
        self.stdout.write(f"evidence={out.resolve()}")
        if g_spike:
            self.stdout.write(
                self.style.SUCCESS(
                    "G-SPIKE CANDIDATE: authorized em HTTP homolog — anexar evidence e marcar gate."
                )
            )
        if inv.status not in {
            NfeInvoice.Status.AUTHORIZED,
            NfeInvoice.Status.POLLING,
            NfeInvoice.Status.REJECTED,
            NfeInvoice.Status.FAILED,
        }:
            raise CommandError(f"estado inesperado: {inv.status}")
