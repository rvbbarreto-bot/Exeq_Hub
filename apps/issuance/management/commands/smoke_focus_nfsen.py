from datetime import date
from decimal import Decimal
import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Tenant
from apps.accounts.secrets import set_tenant_secret
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.polling import poll_nf_issue_status
from apps.issuance.services import cancel_nf_issue, create_nf_issue
from apps.master_data.models import Customer, Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from integrations.nfse.empresas import FocusEmpresaClient
from integrations.nfse.focus import FocusHttpError
from integrations.nfse.municipios import FocusMunicipioClient


class Command(BaseCommand):
    help = "Smoke Focus NFS-e Nacional (Atibaia 3504107) — conectividade + emissão/cancelamento"

    def add_arguments(self, parser):
        parser.add_argument("--ibge", default="3504107")
        parser.add_argument("--emit", action="store_true", help="Cria NfIssue real via Focus HTTP")
        parser.add_argument(
            "--emit-and-cancel",
            action="store_true",
            help="Emite R$1 e cancela na sequência (nota nova)",
        )
        parser.add_argument(
            "--cancel",
            default="",
            help="UUID de NfIssue já autorizada para cancelar no Focus",
        )
        parser.add_argument(
            "--justificativa",
            default="Cancelamento smoke EXEQ Hub homologacao/producao",
            help="Justificativa Focus (15-255 chars)",
        )
        parser.add_argument("--tenant", default="smoke-atibaia")
        parser.add_argument("--amount-cents", type=int, default=100)
        parser.add_argument(
            "--cnpj",
            default="",
            help="CNPJ do prestador já cadastrado/autorizado na Focus (obrigatório com --emit)",
        )

    def handle(self, *args, **options):
        ibge = options["ibge"]
        token = settings.FOCUS_API_TOKEN or ""
        if not token:
            raise CommandError("FOCUS_API_TOKEN ausente no ambiente")

        mun = FocusMunicipioClient(token=token, mode="http")
        try:
            info = mun.get_municipio(ibge)
            exemplo = mun.get_json_exemplo(ibge)
        except FocusHttpError as exc:
            raise CommandError(f"Falha município Focus: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"[OK] município {ibge}"))
        self.stdout.write(f"  keys municipio: {list(info.keys())[:12]}")
        ex_keys = list(exemplo.keys())[:12] if isinstance(exemplo, dict) else type(exemplo)
        self.stdout.write(f"  keys json_exemplo: {ex_keys}")

        cancel_id = (options.get("cancel") or "").strip()
        if cancel_id:
            self._cancel_existing(cancel_id, options["justificativa"])
            return

        if not options["emit"] and not options["emit_and_cancel"]:
            self.stdout.write(
                "Sem --emit/--emit-and-cancel/--cancel: só conectividade."
            )
            return

        cnpj = "".join(ch for ch in (options["cnpj"] or "") if ch.isdigit())
        if len(cnpj) != 14:
            raise CommandError(
                "Com --emit informe --cnpj=14 dígitos do prestador já autorizado na Focus "
                "(painel Minhas Empresas; homolog não expõe GET /v2/empresas)."
            )

        tenant, provider, customer, service, profile = self._ensure_emission_context(
            options=options,
            ibge=ibge,
            cnpj=cnpj,
            token=token,
            mun=mun,
        )

        settings.NF_SYNC_PROCESSING = True
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.FOCUS_HTTP_MODE = "http"

        from django.utils import timezone as dj_tz

        key = f"smoke-{dj_tz.now().strftime('%Y%m%d%H%M%S')}-{options['amount_cents']}"
        try:
            issue = create_nf_issue(
                tenant=tenant,
                idempotency_key=key,
                provider=provider,
                customer=customer,
                service=service,
                fiscal_profile=profile,
                ibge_code=ibge,
                competence_date=date.today(),
                amount_cents=options["amount_cents"],
            )
        except Exception as exc:
            raise CommandError(f"Emissão Focus falhou: {exc}") from exc

        issue = self._wait_authorized(issue)
        self.stdout.write(self.style.SUCCESS(f"[OK] nf_issue={issue.id}"))
        self.stdout.write(f"  status={issue.status}")
        self.stdout.write(f"  focus_ref={issue.focus_ref}")
        self.stdout.write(f"  rejection={issue.rejection_code or '-'}")
        if issue.status == NfIssue.Status.AUTHORIZED:
            self.stdout.write(self.style.SUCCESS("SMOKE EMISSÃO: AUTHORIZED"))
        elif issue.status == NfIssue.Status.POLLING:
            self.stdout.write(
                self.style.WARNING("SMOKE EMISSÃO: POLLING (aguardar webhook/poll)")
            )
        else:
            self.stdout.write(self.style.WARNING(f"SMOKE EMISSÃO: {issue.status}"))
            if issue.focus_status_raw:
                self.stdout.write(f"  raw={issue.focus_status_raw}")

        if options["emit_and_cancel"]:
            if issue.status != NfIssue.Status.AUTHORIZED:
                raise CommandError(
                    f"Não cancelou: emissão em status={issue.status} (precisa authorized)"
                )
            self._cancel_issue(issue, options["justificativa"])

    def _cancel_existing(self, cancel_id: str, justificativa: str) -> None:
        try:
            uuid.UUID(cancel_id)
        except ValueError as exc:
            raise CommandError("--cancel deve ser UUID da NfIssue") from exc
        issue = NfIssue.objects.filter(id=cancel_id).select_related("tenant").first()
        if issue is None:
            raise CommandError(f"NfIssue {cancel_id} não encontrada")
        settings.FOCUS_HTTP_MODE = "http"
        self._cancel_issue(issue, justificativa)

    def _cancel_issue(self, issue: NfIssue, justificativa: str) -> None:
        try:
            cancel_nf_issue(issue, justificativa=justificativa)
        except Exception as exc:
            raise CommandError(f"Cancelamento Focus falhou: {exc}") from exc
        issue.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f"[OK] cancel nf_issue={issue.id}"))
        self.stdout.write(f"  status={issue.status}")
        self.stdout.write(f"  raw={issue.focus_status_raw}")
        if issue.status == NfIssue.Status.CANCELLED:
            self.stdout.write(self.style.SUCCESS("SMOKE CANCELAMENTO: CANCELLED"))
        else:
            self.stdout.write(self.style.WARNING(f"SMOKE CANCELAMENTO: {issue.status}"))

    def _wait_authorized(self, issue: NfIssue) -> NfIssue:
        for _ in range(15):
            issue.refresh_from_db()
            if issue.status == NfIssue.Status.AUTHORIZED:
                return issue
            if issue.status not in {
                NfIssue.Status.POLLING,
                NfIssue.Status.SUBMITTING,
                NfIssue.Status.QUEUED,
            }:
                return issue
            poll_nf_issue_status(issue)
            time.sleep(3)
        issue.refresh_from_db()
        return issue

    def _ensure_emission_context(self, *, options, ibge, cnpj, token, mun):
        tenant, _ = Tenant.objects.get_or_create(
            slug=options["tenant"],
            defaults={
                "legal_name": "Smoke Atibaia LTDA",
                "document": cnpj,
                "focus_layout": "nfsen",
            },
        )
        if tenant.document != cnpj:
            tenant.document = cnpj
            tenant.save(update_fields=["document", "updated_at"])
        set_tenant_secret(
            tenant=tenant,
            provider="focus",
            key_name="api_token",
            plaintext=token,
        )

        provider = Provider.objects.filter(tenant=tenant, document=tenant.document).first()
        if provider is None:
            provider = create_provider(
                tenant=tenant,
                document=tenant.document,
                legal_name=tenant.legal_name,
                tax_regime=TaxRegime.SIMPLES,
                municipal_registration="12345",
                address={
                    "logradouro": "Rua Teste",
                    "numero": "100",
                    "bairro": "Centro",
                    "uf": "SP",
                    "cep": "12940000",
                    "municipio": "Atibaia",
                },
            )

        try:
            FocusEmpresaClient(token=token, mode="http").upsert_empresa_from_provider(
                provider,
                enable_nfsen_homolog=True,
                enable_nfsen_producao=False,
            )
            self.stdout.write(self.style.SUCCESS("[OK] empresa Focus upsert"))
        except FocusHttpError as exc:
            self.stdout.write(
                self.style.WARNING(
                    f"[WARN] empresa Focus API indisponível/erro ({exc}). "
                    "Use empresa já cadastrada no painel Focus."
                )
            )

        tomador_addr = {
            "logradouro": "Rua Almeida Garret",
            "numero": "100",
            "bairro": "Alvinopolis",
            "uf": "SP",
            "cep": "12941410",
            "codigo_municipio": ibge,
        }
        customer = Customer.objects.filter(tenant=tenant, document="00000000000191").first()
        if customer is None:
            customer = create_customer(
                tenant=tenant,
                document="00000000000191",
                document_type="cnpj",
                name="Ficticio Tomador",
                email="test@example.com",
                address=tomador_addr,
            )
        else:
            customer.address = tomador_addr
            customer.save(update_fields=["address", "updated_at"])

        service = ServiceCatalogItem.objects.filter(tenant=tenant, service_code="1.01").first()
        if service is None:
            service = create_service(
                tenant=tenant,
                service_code="1.01",
                description="Servico smoke Atibaia",
                lc116_item="1.01",
                codigo_tributacao_nacional_iss="010701",
            )
        else:
            service.codigo_tributacao_nacional_iss = (
                service.codigo_tributacao_nacional_iss or "010701"
            )
            service.save(update_fields=["codigo_tributacao_nacional_iss", "updated_at"])

        profile = FiscalProfile.objects.filter(tenant=tenant, name="SN-Smoke").first()
        overrides = {
            "codigo_tributacao_nacional_iss": "010701",
            "codigo_nbs": "115013000",
            "tipo_retencao_iss": 1,
            "tributacao_iss": 1,
            "regime_especial_tributacao": 0,
            **mun.suggested_overrides(ibge),
        }
        if profile is None:
            profile = FiscalProfile.objects.create(
                tenant=tenant,
                name="SN-Smoke",
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
                simples_codigo_tributacao=3,
                valid_from=date(2024, 1, 1),
                focus_field_overrides=overrides,
            )
            catalog.publish_checklist = {
                "csv_validated": True,
                "rules_reviewed": True,
                "terms_accepted": True,
            }
            catalog.save(update_fields=["publish_checklist"])
            publish_catalog(catalog)
        else:
            MunicipalTaxRule.objects.filter(
                tenant=tenant,
                fiscal_profile=profile,
                ibge_code=ibge,
                service_code="1.01",
            ).update(focus_field_overrides=overrides)

        return tenant, provider, customer, service, profile
