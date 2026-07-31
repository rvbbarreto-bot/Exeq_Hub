"""M3 — emissão E2E Hub (create_nf_issue → SEFIN → authorized + artefatos).

Uso (Atibaia só em produção SEFIN):
  python manage.py smoke_sefin_hub_emit --tenant-cert agendador-qa --cnpj 37229907000137 ^
      --environment production --valor 15.00 --cTribNac 170101
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from apps.accounts.models import Tenant
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfArtifact, NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import Customer, Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


class Command(BaseCommand):
    help = "M3: cria NfIssue no Hub e emite via SEFIN HTTP (sync)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-cert", default="agendador-qa")
        parser.add_argument("--cnpj", default="37229907000137")
        parser.add_argument("--ibge", default="3504107")
        parser.add_argument("--cTribNac", default="170101")
        parser.add_argument("--valor", default="15.00")
        parser.add_argument("--tomador-cpf", default="26391118841")
        parser.add_argument(
            "--tomador-nome",
            default="MARIA CAROLINA DE OLIVEIRA VITORIANO",
        )
        parser.add_argument("--cep", default="12941480")
        parser.add_argument("--environment", default="production")
        parser.add_argument("--out", default=".storage/sefin_m3_hub_e2e_evidence.json")

    def handle(self, *args, **options):
        slug = options["tenant_cert"]
        cnpj = "".join(ch for ch in options["cnpj"] if ch.isdigit())
        ibge = "".join(ch for ch in options["ibge"] if ch.isdigit()).zfill(7)
        c_trib = "".join(ch for ch in options["cTribNac"] if ch.isdigit()).zfill(6)[:6]
        cep = "".join(ch for ch in options["cep"] if ch.isdigit()).zfill(8)[-8:]
        cpf = "".join(ch for ch in options["tomador_cpf"] if ch.isdigit())
        amount_cents = int(
            (Decimal(str(options["valor"])).quantize(Decimal("0.01")) * 100)
        )

        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {slug}") from exc

        provider, customer, service, profile = self._ensure_master_data(
            tenant=tenant,
            cnpj=cnpj,
            ibge=ibge,
            c_trib=c_trib,
            cpf=cpf,
            tomador_nome=options["tomador_nome"],
            cep=cep,
        )

        env = options["environment"]
        idem = f"sefin-hub-e2e-{uuid.uuid4().hex[:12]}"
        with override_settings(
            SEFIN_HTTP_MODE="http",
            SEFIN_ENVIRONMENT=env,
            NF_SYNC_PROCESSING=True,
            NFSE_DEFAULT_PROVIDER="sefin",
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
                amount_cents=amount_cents,
            )

        issue.refresh_from_db()
        arts = list(
            NfArtifact.objects.filter(nf_issue=issue).values_list("kind", flat=True)
        )
        evidence = {
            "tenant": slug,
            "issue_id": str(issue.id),
            "status": issue.status,
            "focus_ref": issue.focus_ref,
            "rejection_code": issue.rejection_code,
            "artifacts": arts,
            "sefin_environment": env,
            "sefin_http_mode": "http",
            "settings_default_provider": settings.NFSE_DEFAULT_PROVIDER,
            "raw_http_status": (issue.focus_status_raw or {}).get("http_status"),
            "erros": (issue.focus_status_raw or {}).get("erros")
            or (issue.focus_status_raw or {}).get("data", {}).get("erros"),
        }
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

        if issue.status == NfIssue.Status.AUTHORIZED:
            self.stdout.write(self.style.SUCCESS(f"M3 OK authorized chave={issue.focus_ref}"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"M3 status={issue.status} ref={issue.focus_ref} "
                    f"rej={issue.rejection_code}"
                )
            )
            raw = issue.focus_status_raw or {}
            self.stdout.write(json.dumps(raw, ensure_ascii=False, indent=2)[:2000])
        self.stdout.write(self.style.SUCCESS(f"Evidência: {out}"))

    def _ensure_master_data(
        self,
        *,
        tenant,
        cnpj: str,
        ibge: str,
        c_trib: str,
        cpf: str,
        tomador_nome: str,
        cep: str,
    ):
        provider = Provider.objects.filter(tenant=tenant, document=cnpj).first()
        if provider is None:
            provider = create_provider(
                tenant=tenant,
                document=cnpj,
                legal_name="EXEQ TECNOLOGIA LTDA",
                tax_regime=TaxRegime.SIMPLES,
            )
        else:
            if provider.tax_regime != TaxRegime.SIMPLES:
                provider.tax_regime = TaxRegime.SIMPLES
                provider.save(update_fields=["tax_regime", "updated_at"])

        customer = Customer.objects.filter(tenant=tenant, document=cpf).first()
        addr = {
            "codigo_municipio": ibge,
            "cep": cep,
            "logradouro": "Rua Spike",
            "numero": "1",
            "bairro": "Centro",
        }
        if customer is None:
            customer = create_customer(
                tenant=tenant,
                document=cpf,
                document_type=Customer.DocumentType.CPF,
                name=tomador_nome,
                address=addr,
            )
        else:
            customer.name = tomador_nome
            customer.address = addr
            customer.save(update_fields=["name", "address", "updated_at"])

        service = ServiceCatalogItem.objects.filter(
            tenant=tenant, service_code=c_trib
        ).first()
        if service is None:
            service = create_service(
                tenant=tenant,
                service_code=c_trib,
                description="Servico spike Hub SEFIN EXEQ",
                codigo_tributacao_nacional_iss=c_trib,
                lc116_item=f"{c_trib[:2]}.{c_trib[2:4]}",
            )
        elif not service.codigo_tributacao_nacional_iss:
            service.codigo_tributacao_nacional_iss = c_trib
            service.save(update_fields=["codigo_tributacao_nacional_iss", "updated_at"])

        profile = FiscalProfile.objects.filter(
            tenant=tenant, name="SN-SEFIN-M3", tax_regime=TaxRegime.SIMPLES
        ).first()
        if profile is None:
            profile = FiscalProfile.objects.create(
                tenant=tenant,
                name="SN-SEFIN-M3",
                tax_regime=TaxRegime.SIMPLES,
            )

        from apps.fiscal.models import MunicipalTaxRule, TaxRuleCatalog

        catalog = TaxRuleCatalog.objects.filter(
            tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
        ).first()
        if catalog is None:
            catalog = create_catalog(tenant=tenant)
            add_rule(
                catalog=catalog,
                fiscal_profile=profile,
                ibge_code=ibge,
                municipio_nome="Atibaia",
                uf="SP",
                service_code=c_trib,
                tax_regime=TaxRegime.SIMPLES,
                iss_rate=Decimal("0.0200"),
                simples_codigo_tributacao=3,
                valid_from=date(2024, 1, 1),
            )
            catalog.publish_checklist = {
                "csv_validated": True,
                "rules_reviewed": True,
                "terms_accepted": True,
            }
            catalog.save(update_fields=["publish_checklist"])
            publish_catalog(catalog)
        else:
            exists = MunicipalTaxRule.objects.filter(
                tenant=tenant,
                catalog=catalog,
                fiscal_profile=profile,
                ibge_code=ibge,
                service_code=c_trib,
                tax_regime=TaxRegime.SIMPLES,
            ).exists()
            if not exists:
                add_rule(
                    catalog=catalog,
                    fiscal_profile=profile,
                    ibge_code=ibge,
                    municipio_nome="Atibaia",
                    uf="SP",
                    service_code=c_trib,
                    tax_regime=TaxRegime.SIMPLES,
                    iss_rate=Decimal("0.0200"),
                    simples_codigo_tributacao=3,
                    valid_from=date(2024, 1, 1),
                )

        return provider, customer, service, profile
