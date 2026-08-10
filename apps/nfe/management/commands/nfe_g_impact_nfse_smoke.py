"""I8 G-IMPACT — smoke NFS-e stub no mesmo release da onda NF-e.

Prova de não-regressão do caminho de emissão NFS-e (stub, sem SEFIN real):

  python manage.py nfe_g_impact_nfse_smoke --tenant acme

Exit 0 se NFS-e authorized; exit 1 se falhou (bloqueia checklist de release).
NFE_ENABLED permanece default off — este comando não habilita flag de prod.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from apps.accounts.models import Tenant
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import Provider, TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


class Command(BaseCommand):
    help = (
        "G-IMPACT-OK checklist: emite 1 NFS-e em stub (create_nf_issue). "
        "Não toca SEFIN HTTP; não habilita NFE_ENABLED em produção. "
        "Use no release junto com artefatos NF-e I1–I2/UI downloads."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug do tenant")
        parser.add_argument("--cnpj", default="37229907000137")
        parser.add_argument("--ibge", default="3504107")
        parser.add_argument("--valor-cents", type=int, default=1000)
        parser.add_argument("--out", default=".storage/nfe_g_impact_nfse_evidence.json")

    def handle(self, *args, **options):
        slug = options["tenant"]
        cnpj = "".join(ch for ch in options["cnpj"] if ch.isdigit())
        ibge = "".join(ch for ch in options["ibge"] if ch.isdigit()).zfill(7)

        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {slug}") from exc

        provider = Provider.objects.filter(tenant=tenant, document=cnpj).first()
        if provider is None:
            provider = create_provider(
                tenant=tenant,
                document=cnpj,
                legal_name="PRESTADOR G-IMPACT NFE WAVE",
                tax_regime=TaxRegime.SIMPLES,
            )

        customer = create_customer(
            tenant=tenant,
            document="52998224725",
            document_type="cpf",
            name="Tomador G-IMPACT",
        )
        service = create_service(
            tenant=tenant,
            service_code="1.01",
            description="Servico G-IMPACT release NFe",
            codigo_tributacao_nacional_iss="010701",
        )
        profile = FiscalProfile.objects.filter(tenant=tenant).first()
        if profile is None:
            profile = FiscalProfile.objects.create(
                tenant=tenant,
                name="SN-G-IMPACT",
                tax_regime=TaxRegime.SIMPLES,
            )
        catalog = create_catalog(tenant=tenant)
        add_rule(
            catalog=catalog,
            fiscal_profile=profile,
            ibge_code=ibge,
            municipio_nome="Atibaia",
            uf="SP",
            service_code="1.01",
            tax_regime=TaxRegime.SIMPLES,
            iss_rate=Decimal("0.0200"),
            valid_from=date(2024, 1, 1),
        )
        catalog.publish_checklist = {
            "csv_validated": True,
            "rules_reviewed": True,
            "terms_accepted": True,
        }
        catalog.save(update_fields=["publish_checklist"])
        publish_catalog(catalog)

        idem = f"nfe-g-impact-{uuid.uuid4().hex[:12]}"
        with override_settings(
            NF_SYNC_PROCESSING=True,
            FOCUS_HTTP_MODE="stub",
            SEFIN_HTTP_MODE="stub",
            NFSE_DEFAULT_PROVIDER="focus",
            # Não liga NFE_ENABLED — isolamento
            NFE_ENABLED=False,
        ):
            issue = create_nf_issue(
                tenant=tenant,
                idempotency_key=idem,
                provider=provider,
                customer=customer,
                service=service,
                fiscal_profile=profile,
                ibge_code=ibge,
                competence_date=date.today(),
                amount_cents=int(options["valor_cents"]),
            )

        issue.refresh_from_db()
        ok = issue.status == NfIssue.Status.AUTHORIZED
        evidence = {
            "ticket": "I8",
            "gate": "G-IMPACT-OK",
            "g_impact_ok": ok,
            "tenant": slug,
            "nf_issue_id": str(issue.id),
            "status": issue.status,
            "focus_ref": issue.focus_ref or "",
            "nfe_enabled_during_smoke": False,
            "provider": "focus/stub",
            "note": (
                "NFS-e stub authorized — sem regressão aparente no InvoiceEngine. "
                if ok
                else "FALHA: NFS-e não authorized — bloquear release onda NF-e."
            ),
        }
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(f"NFS-e status={issue.status} evidence={out.resolve()}")
        if not ok:
            raise CommandError(f"G-IMPACT-FAIL: status={issue.status}")
        self.stdout.write(self.style.SUCCESS("G-IMPACT-OK (NFS-e stub authorized)"))
