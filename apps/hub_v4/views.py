"""Views da shell operacional Hub V4 — operação multi-CNPJ + create_nf_issue."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views import View
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.auth_services import authenticate_for_tenant
from apps.accounts.membership_services import (
    ASSIGNABLE_ROLE_CODES,
    invite_or_link_user,
    update_membership,
)
from apps.accounts.models import TenantMembership, TenantRole, User
from apps.accounts.permissions import ADMIN_ROLES, FOOD_ONLY_ROLES, WRITE_ROLES
from apps.accounts.plan_limits import provider_usage
from apps.accounts.services import ensure_system_roles
from apps.billing.models import Charge
from apps.das.models import GuiaFiscal
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.hub_v4.active_company import get_active_provider, set_active_provider
from apps.hub_v4.auth import clear_hub_session, require_hub, set_hub_session
from apps.hub_v4.documents import artifact_presence, download_nf_artifact
from apps.hub_v4.nfe_hub import download_nfe_artifact, nfe_artifact_flags
from apps.hub_v4.forms import (
    provider_form_error_message,
    save_customer_from_post,
    save_fiscal_profile_from_post,
    save_nfe_product_from_post,
    save_provider_from_post,
    save_service_from_post,
    save_tax_rule_from_post,
)
from apps.hub_v4.nav_flags import nfe_enabled_for_tenant
from apps.hub_v4.services import (
    certificate_rows,
    dashboard_context,
    issue_timeline,
    nfse_queryset,
)
from apps.issuance.exceptions import FiscalProfileRequiredError, InvalidTransitionError
from apps.issuance.models import NfArtifact, NfIssue, NfIssueEvent
from apps.issuance.services import create_nf_issue, save_nf_draft
from apps.master_data.models import Customer, Provider, ServiceCatalogItem, TaxRegime
from apps.master_data.services import ensure_services_for_wizard, lookup_document
from apps.nfe.listing import filter_invoice_queryset
from apps.nfe.models import NfeInvoice, NfeProduct
from apps.nfe.services import (
    allowed_actions,
    cancel_invoice,
    create_draft,
    emit_invoice,
    issue_carta_correcao,
    replace_items,
)
from django.conf import settings as dj_settings
from integrations.cadastro.exceptions import (
    CadastroCpfLookupNotSupportedError,
    CadastroDocumentInvalidError,
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)
from shared.exceptions import AuthenticationError
from shared.validators import validate_cnpj
from shared.crypto import CryptoError
from apps.accounts.certificates import PfxParseError, upload_a1_certificate


def _require_writer_hub(request: HttpRequest):
    tenant, user, role, redir = require_hub(request)
    if redir:
        return None, None, None, redir
    if role not in WRITE_ROLES:
        messages.error(request, "Seu papel não permite editar cadastros.")
        return tenant, user, role, redirect("hub-v4-dashboard")
    return tenant, user, role, None


def _require_tenant_admin_hub(request: HttpRequest):
    tenant, user, role, redir = require_hub(request)
    if redir:
        return None, None, None, redir
    if role not in ADMIN_ROLES:
        messages.error(request, "Apenas administradores do escritório gerenciam usuários.")
        return tenant, user, role, redirect("hub-v4-dashboard")
    return tenant, user, role, None


def _greeting_user(user) -> str:
    from django.utils import timezone

    name = (user.name or user.email or "usuário").strip()
    first = name.split()[0] if name else "usuário"
    hour = timezone.localtime().hour
    if hour < 12:
        prefix = "Bom dia"
    elif hour < 18:
        prefix = "Boa tarde"
    else:
        prefix = "Boa noite"
    return f"{prefix}, {first}"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class HubLoginView(View):
    template_name = "hub_v4/login.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir is None:
            return redirect("hub-v4-dashboard")
        return render(request, self.template_name)

    def post(self, request: HttpRequest):
        tenant_slug = (request.POST.get("tenant_slug") or "").strip()
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        try:
            user, membership = authenticate_for_tenant(
                tenant_slug=tenant_slug, email=email, password=password
            )
        except AuthenticationError as exc:
            return render(
                request,
                self.template_name,
                {"error": str(exc) or "Credenciais inválidas."},
            )
        set_hub_session(
            request,
            user=user,
            tenant=membership.tenant,
            role_code=membership.role.code,
        )
        if membership.role.code in FOOD_ONLY_ROLES:
            return redirect("hub-v4-food-orders")
        return redirect("hub-v4-dashboard")


@require_http_methods(["POST"])
def hub_logout(request: HttpRequest):
    clear_hub_session(request)
    return redirect("hub-v4-login")


class DashboardView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        if role in FOOD_ONLY_ROLES:
            return redirect("hub-v4-food-orders")
        ctx = dashboard_context(tenant)
        ctx.update(
            {
                "nav": "dashboard",
                "page_title": "Painel",
                "greeting": _greeting_user(user),
                "role_code": role,
            }
        )
        return render(request, "hub_v4/dashboard.html", ctx)


class NfseListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        status = request.GET.get("status") or "all"
        q = request.GET.get("q") or ""
        qs = nfse_queryset(tenant, status=status, q=q)
        qs = qs.annotate(
            has_pdf=Exists(
                NfArtifact.objects.filter(
                    nf_issue_id=OuterRef("pk"), kind=NfArtifact.Kind.PDF
                )
            ),
            has_xml=Exists(
                NfArtifact.objects.filter(
                    nf_issue_id=OuterRef("pk"), kind=NfArtifact.Kind.XML
                )
            ),
        )
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        chips = []
        if status and status != "all":
            chips.append({"key": "status", "label": f"Status: {status}"})
        if q:
            chips.append({"key": "q", "label": f"Busca: {q}"})
        return render(
            request,
            "hub_v4/nfse/list.html",
            {
                "nav": "nfse",
                "page_title": "NFS-e",
                "page": page,
                "status": status,
                "q": q,
                "chips": chips,
                "role_code": role,
            },
        )


class NfseDetailView(View):
    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        issue = get_object_or_404(
            NfIssue.objects.select_related("customer", "provider", "service"),
            pk=pk,
            tenant=tenant,
        )
        events = NfIssueEvent.objects.filter(nf_issue=issue).order_by("occurred_at")
        artifacts = issue.artifacts.select_related("stored_file").all()
        docs = artifact_presence(issue)
        from apps.issuance.sefin_summary import sefin_integration_summary

        sefin = sefin_integration_summary(issue)
        from integrations.nfse.emission_text import resolve_emission_text

        descricao_nota, info_compl = resolve_emission_text(issue)
        return render(
            request,
            "hub_v4/nfse/detail.html",
            {
                "nav": "nfse",
                "page_title": f"NFS-e · {issue.focus_ref or str(issue.id)[:8]}",
                "issue": issue,
                "descricao_nota": descricao_nota,
                "informacoes_complementares": info_compl,
                "timeline": issue_timeline(issue),
                "events": events,
                "artifacts": artifacts,
                "docs": docs,
                "role_code": role,
                "sefin": sefin,
            },
        )


class NfseDocumentsView(View):
    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        issue = get_object_or_404(NfIssue, pk=pk, tenant=tenant)
        artifacts = list(issue.artifacts.select_related("stored_file").all())
        by_kind = {a.kind: a for a in artifacts}
        payload = issue.internal_payload or issue.focus_status_raw or {}
        tab = (request.GET.get("tab") or "pdf").lower()
        if tab not in {"pdf", "xml", "json", "headers", "logs"}:
            tab = "pdf"
        return render(
            request,
            "hub_v4/nfse/documents.html",
            {
                "nav": "nfse",
                "page_title": "Documentos Técnicos",
                "issue": issue,
                "by_kind": by_kind,
                "docs": artifact_presence(issue),
                "active_tab": tab,
                "payload_json": json.dumps(
                    payload, ensure_ascii=False, indent=2, default=str
                ),
                "headers_json": json.dumps(
                    (issue.focus_status_raw or {}).get("headers")
                    if isinstance(issue.focus_status_raw, dict)
                    else {},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "role_code": role,
            },
        )


@require_GET
def nfse_document_download(request: HttpRequest, pk, kind: str):
    tenant, user, role, redir = require_hub(request)
    if redir:
        return redir
    return download_nf_artifact(tenant=tenant, issue_id=pk, kind=kind)


@require_http_methods(["GET", "POST"])
def nfse_lookup_customer(request: HttpRequest):
    """Lookup CNPJ (etapa Tomador) via JSON — não emite nota."""
    tenant, user, role, redir = require_hub(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Não autenticado"}, status=401)
    raw = request.GET.get("document") or request.POST.get("document") or ""
    doc = "".join(ch for ch in raw if ch.isdigit())
    # Já cadastrado no tenant?
    existing = Customer.objects.filter(tenant=tenant, document=doc).first()
    if existing:
        phone = ""
        addr = existing.address or {}
        if isinstance(addr, dict):
            phone = addr.get("telefone") or addr.get("phone") or ""
        return JsonResponse(
            {
                "ok": True,
                "source": "tenant",
                "data": {
                    "customer_id": str(existing.id),
                    "document": existing.document,
                    "name": existing.name,
                    "email": existing.email or "",
                    "phone": phone,
                    "message": "✓ Tomador encontrado",
                },
            }
        )
    try:
        data = lookup_document(tenant=tenant, document=doc, entity_kind="customer")
        addr = data.address.as_dict() if hasattr(data.address, "as_dict") else {}
        return JsonResponse(
            {
                "ok": True,
                "source": "receita",
                "data": {
                    "customer_id": "",
                    "document": data.document,
                    "name": data.legal_name,
                    "email": data.email or "",
                    "phone": data.telefone or "",
                    "address": addr,
                    "message": "✓ Tomador encontrado (Receita — selecione/cadastrar)",
                },
            }
        )
    except (
        CadastroCpfLookupNotSupportedError,
        CadastroDocumentInvalidError,
        CadastroNotFoundError,
        CadastroProviderUnavailableError,
    ) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


class NfseWizardView(View):
    template_name = "hub_v4/nfse/wizard.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        draft = self._load_draft(request, tenant)
        if request.GET.get("draft") and draft is None:
            messages.error(request, "Rascunho não encontrado ou já emitido.")
            return redirect("hub-v4-nfse-list")
        return render(
            request,
            self.template_name,
            self._context(tenant, role, request=request, draft=draft),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir

        action = (request.POST.get("wizard_action") or "").strip()
        confirm = request.POST.get("confirm_emit") == "1"
        save_draft = action == "save_draft"

        if not save_draft and not confirm:
            messages.error(request, "Confirmação obrigatória para emitir.")
            return render(
                request,
                self.template_name,
                {
                    **self._context(
                        tenant,
                        role,
                        request=request,
                        draft=self._draft_from_post(request, tenant),
                        form_post=request.POST,
                        wizard_initial_step=3,
                    ),
                },
            )

        try:
            payload = self._parse_wizard_payload(request, tenant)
            draft = payload.pop("draft")
            if save_draft:
                issue = save_nf_draft(draft=draft, **payload)
            else:
                from apps.fiscal.readiness import (
                    FiscalReadinessError,
                    assert_emit_rule_cover,
                )

                try:
                    assert_emit_rule_cover(
                        tenant=tenant,
                        fiscal_profile=payload.get("fiscal_profile"),
                        ibge_code=payload.get("ibge_code") or "",
                        service_code=getattr(
                            payload.get("service"), "service_code", ""
                        )
                        or "",
                        competence_date=payload.get("competence_date"),
                        service=payload.get("service"),
                    )
                except FiscalReadinessError as exc:
                    raise ValueError(str(exc)) from exc
                from apps.fiscal.compliance_hints import service_cnae_compliance_warnings

                for hint in service_cnae_compliance_warnings(
                    provider=payload.get("provider"),
                    service=payload.get("service"),
                ):
                    messages.warning(request, hint)
                issue = create_nf_issue(**{
                    k: v
                    for k, v in payload.items()
                    if k
                    in {
                        "tenant",
                        "idempotency_key",
                        "provider",
                        "customer",
                        "service",
                        "fiscal_profile",
                        "ibge_code",
                        "competence_date",
                        "amount_cents",
                        "descricao_servico",
                        "informacoes_complementares",
                    }
                })
            pid = request.POST.get("provider_id")
            if pid:
                set_active_provider(request, tenant, pid)
        except (ValueError, FiscalProfileRequiredError, InvalidTransitionError) as exc:
            messages.error(request, str(exc) or "Falha ao processar a nota.")
            return render(
                request,
                self.template_name,
                {
                    **self._context(
                        tenant,
                        role,
                        request=request,
                        draft=self._draft_from_post(request, tenant),
                        form_post=request.POST,
                        wizard_initial_step=3,
                    ),
                },
            )
        except Exception as exc:
            messages.error(request, str(exc) or "Falha ao processar a nota.")
            return render(
                request,
                self.template_name,
                {
                    **self._context(
                        tenant,
                        role,
                        request=request,
                        draft=self._draft_from_post(request, tenant),
                        form_post=request.POST,
                        wizard_initial_step=3,
                    ),
                },
            )

        if save_draft:
            messages.success(request, "Rascunho salvo. Você pode retomar a emissão a qualquer momento.")
            return redirect(f"{reverse('hub-v4-nfse-wizard')}?draft={issue.id}")
        messages.success(request, "NFS-e enviada para autorização.")
        return redirect("hub-v4-nfse-detail", pk=issue.id)

    def _load_draft(self, request, tenant) -> NfIssue | None:
        draft_id = (request.GET.get("draft") or "").strip()
        if not draft_id:
            return None
        return (
            NfIssue.objects.filter(
                pk=draft_id, tenant=tenant, status=NfIssue.Status.DRAFT
            )
            .select_related("provider", "customer", "service", "fiscal_profile")
            .first()
        )

    def _draft_from_post(self, request, tenant) -> NfIssue | None:
        draft_id = (request.POST.get("draft_id") or "").strip()
        if not draft_id:
            return None
        return (
            NfIssue.objects.filter(
                pk=draft_id, tenant=tenant, status=NfIssue.Status.DRAFT
            )
            .select_related("provider", "customer", "service", "fiscal_profile")
            .first()
        )

    def _context(
        self,
        tenant,
        role,
        request=None,
        draft=None,
        form_post=None,
        wizard_initial_step: int = 0,
    ):
        customers = list(
            Customer.objects.filter(tenant=tenant, is_active=True).order_by("name")[:200]
        )
        services = ensure_services_for_wizard(tenant=tenant, limit=500)
        profiles = list(FiscalProfile.objects.filter(tenant=tenant)[:50])
        providers = list(
            Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
        )
        active = get_active_provider(request, tenant) if request is not None else None
        active_id = str(active.id) if active else ""
        if draft and draft.provider_id:
            active_id = str(draft.provider_id)
        customers_json = [
            {
                "id": str(c.id),
                "name": c.name,
                "document": c.document,
                "email": c.email or "",
                "phone": (c.address or {}).get("telefone", "")
                if isinstance(c.address, dict)
                else "",
            }
            for c in customers
        ]
        services_json = [
            {
                "id": str(s.id),
                "code": s.service_code,
                "lc116": s.lc116_item or "",
                "description": s.description,
            }
            for s in services
        ]
        profiles_json = [
            {
                "id": str(p.id),
                "name": p.name,
                "tax_regime": p.tax_regime,
                "iss_retention_policy": p.iss_retention_policy,
                "is_simples": p.tax_regime == TaxRegime.SIMPLES
                or p.tax_regime == "simples_nacional",
            }
            for p in profiles
        ]
        amount_display = ""
        if draft and draft.amount_cents:
            amount_display = f"{Decimal(draft.amount_cents) / Decimal(100):.2f}".replace(
                ".", ","
            )
        draft_emission = (
            (draft.internal_payload or {}).get("emission")
            if draft and isinstance(draft.internal_payload, dict)
            else {}
        ) or {}
        draft_service_desc = draft_emission.get("descricao_servico") or (
            draft.service.description if draft else ""
        )
        draft_info_compl = draft_emission.get("informacoes_complementares") or ""
        selected_customer_id = str(draft.customer_id) if draft else ""
        selected_service_id = str(draft.service_id) if draft else ""
        selected_profile_id = (
            str(draft.fiscal_profile_id) if draft and draft.fiscal_profile_id else ""
        )
        draft_competence = (
            draft.competence_date.isoformat() if draft else date.today().isoformat()
        )
        draft_ibge = draft.ibge_code if draft else ""
        idempotency_key = draft.idempotency_key if draft else f"hub-v4-{uuid.uuid4()}"
        draft_id = str(draft.id) if draft else ""

        from apps.fiscal.multimunicipio import list_published_ibge_codes, provider_default_ibge

        published_ibge = list_published_ibge_codes(tenant=tenant)
        if not draft_ibge and providers:
            first = providers[0]
            draft_ibge = provider_default_ibge(first)

        if form_post is not None:
            post_amount = (form_post.get("amount") or "").strip()
            if post_amount:
                amount_display = post_amount
            post_customer = (form_post.get("customer_id") or "").strip()
            if post_customer:
                selected_customer_id = post_customer
            post_service = (form_post.get("service_id") or "").strip()
            if post_service:
                selected_service_id = post_service
            post_profile = (form_post.get("fiscal_profile_id") or "").strip()
            if post_profile:
                selected_profile_id = post_profile
            post_comp = (form_post.get("competence_date") or "").strip()
            if post_comp:
                draft_competence = post_comp
            post_ibge = (form_post.get("ibge_code") or "").strip()
            if post_ibge:
                draft_ibge = post_ibge
            post_desc = (form_post.get("service_description") or "").strip()
            if post_desc:
                draft_service_desc = post_desc
            draft_info_compl = (form_post.get("informacoes_complementares") or "").strip()
            post_provider = (form_post.get("provider_id") or "").strip()
            if post_provider:
                active_id = post_provider
            post_idem = (form_post.get("idempotency_key") or "").strip()
            if post_idem:
                idempotency_key = post_idem
            post_draft_id = (form_post.get("draft_id") or "").strip()
            if post_draft_id:
                draft_id = post_draft_id

        return {
            "nav": "nfse",
            "page_title": "Continuar rascunho" if draft else "Emitir NFS-e",
            "providers": providers,
            "active_provider_id": active_id,
            "services": services,
            "customers": customers,
            "profiles": profiles,
            "customers_data": customers_json,
            "services_data": services_json,
            "profiles_data": profiles_json,
            "role_code": role,
            "today": date.today().isoformat(),
            "idempotency_key": idempotency_key,
            "draft": draft,
            "draft_id": draft_id,
            "selected_customer_id": selected_customer_id,
            "selected_service_id": selected_service_id,
            "selected_profile_id": selected_profile_id,
            "draft_competence": draft_competence,
            "draft_amount": amount_display,
            "draft_ibge": draft_ibge,
            "draft_service_desc": draft_service_desc,
            "draft_info_compl": draft_info_compl,
            "wizard_initial_step": wizard_initial_step,
            "regime_simples": TaxRegime.SIMPLES,
            "published_ibge": published_ibge,
        }

    def _parse_wizard_payload(self, request, tenant) -> dict:
        provider = get_object_or_404(
            Provider, pk=request.POST.get("provider_id"), tenant=tenant
        )
        customer = get_object_or_404(
            Customer, pk=request.POST.get("customer_id"), tenant=tenant
        )
        service = get_object_or_404(
            ServiceCatalogItem, pk=request.POST.get("service_id"), tenant=tenant
        )
        profile_id = request.POST.get("fiscal_profile_id")
        if profile_id:
            profile = get_object_or_404(FiscalProfile, pk=profile_id, tenant=tenant)
        else:
            profile = FiscalProfile.objects.filter(tenant=tenant).first()
        if profile is None:
            raise FiscalProfileRequiredError(
                "Cadastre um perfil fiscal antes de emitir."
            )

        from apps.hub_v4.forms import parse_brl_amount_cents

        cents = parse_brl_amount_cents(
            request.POST.get("amount") or "",
            field_label="Valor",
        )

        competence = request.POST.get("competence_date") or date.today().isoformat()
        from apps.fiscal.multimunicipio import resolve_wizard_ibge_code

        ibge = resolve_wizard_ibge_code(
            post_ibge=request.POST.get("ibge_code") or "",
            provider=provider,
        )
        draft = self._draft_from_post(request, tenant)
        idem = (
            (draft.idempotency_key if draft else None)
            or request.POST.get("idempotency_key")
            or f"hub-v4-{uuid.uuid4()}"
        )
        descricao = (request.POST.get("service_description") or "").strip()
        if not descricao:
            descricao = service.description
        if not descricao:
            raise ValueError("Informe a descrição do serviço na nota.")
        info_compl = (request.POST.get("informacoes_complementares") or "").strip()
        return {
            "tenant": tenant,
            "idempotency_key": idem,
            "provider": provider,
            "customer": customer,
            "service": service,
            "fiscal_profile": profile,
            "ibge_code": str(ibge)[:7],
            "competence_date": date.fromisoformat(competence),
            "amount_cents": cents,
            "draft": draft,
            "descricao_servico": descricao,
            "informacoes_complementares": info_compl,
        }





class ChargesListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        qs = (
            Charge.objects.filter(tenant=tenant)
            .select_related("customer")
            .order_by("-created_at")
        )
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/charges/list.html",
            {
                "nav": "charges",
                "page_title": "Cobranças",
                "page": page,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
            },
        )


class ChargeCreateView(View):
    template_name = "hub_v4/charges/form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        return render(request, self.template_name, self._ctx(tenant, role, request))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        try:
            charge_or_list = self._create(request, tenant)
        except Exception as exc:
            messages.error(request, str(exc) or "Falha ao emitir cobrança.")
            return render(
                request,
                self.template_name,
                {**self._ctx(tenant, role, request), "form": request.POST},
            )
        if isinstance(charge_or_list, list):
            n = len(charge_or_list)
            first = charge_or_list[0]
            messages.success(
                request,
                f"{n} cobrança(s) emitida(s). Grupo agenda {first.schedule_group_id}.",
            )
            return redirect("hub-v4-charge-detail", pk=first.id)
        messages.success(request, "Cobrança emitida no gateway.")
        return redirect("hub-v4-charge-detail", pk=charge_or_list.id)

    def _ctx(self, tenant, role, request):
        customers = Customer.objects.filter(tenant=tenant, is_active=True).order_by(
            "name"
        )[:300]
        return {
            "nav": "charges",
            "page_title": "Nova cobrança",
            "role_code": role,
            "customers": customers,
            "kinds": Charge.ChargeKind.choices,
            "idempotency_key": f"hub-chg-{uuid.uuid4()}",
            "default_due": (date.today()).isoformat(),
        }

    def _create(self, request, tenant):
        from apps.billing.exceptions import (
            GatewayRegistrationError,
            InvalidChargeInputError,
        )
        from apps.billing.services import create_charge

        customer = get_object_or_404(
            Customer, pk=request.POST.get("customer_id"), tenant=tenant
        )
        raw_amount = (request.POST.get("amount") or "0").strip()
        if "," in raw_amount:
            raw_amount = raw_amount.replace(".", "").replace(",", ".")
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation as exc:
            raise ValueError("Valor inválido") from exc
        cents = int((amount * 100).quantize(Decimal("1")))
        due = request.POST.get("due_date") or date.today().isoformat()
        kind = (request.POST.get("charge_kind") or Charge.ChargeKind.SIMPLE).strip()
        inst_raw = (request.POST.get("installment_count") or "").strip()
        installment_count = int(inst_raw) if inst_raw.isdigit() else None
        rec_end = (request.POST.get("recurrence_end_date") or "").strip() or None
        try:
            return create_charge(
                tenant=tenant,
                idempotency_key=request.POST.get("idempotency_key")
                or f"hub-chg-{uuid.uuid4()}",
                customer=customer,
                amount_cents=cents,
                due_date=date.fromisoformat(due),
                description=(request.POST.get("description") or "").strip(),
                seu_numero=(request.POST.get("seu_numero") or "").strip() or None,
                charge_kind=kind,
                installment_count=installment_count,
                recurrence_end_date=date.fromisoformat(rec_end) if rec_end else None,
            )
        except (InvalidChargeInputError, GatewayRegistrationError, ValueError) as exc:
            raise ValueError(str(exc)) from exc


class ChargeDetailView(View):
    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        charge = get_object_or_404(
            Charge.objects.select_related("customer"),
            pk=pk,
            tenant=tenant,
        )
        return render(
            request,
            "hub_v4/charges/detail.html",
            {
                "nav": "charges",
                "page_title": "Cobrança",
                "charge": charge,
                "role_code": role,
            },
        )


class DasListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        qs = (
            GuiaFiscal.objects.filter(tenant=tenant)
            .select_related("provider")
            .order_by("-created_at")
        )
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/das/list.html",
            {
                "nav": "das",
                "page_title": "Guias DAS",
                "page": page,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
            },
        )


class DasEmitView(View):
    template_name = "hub_v4/das/form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        return render(request, self.template_name, self._ctx(tenant, role, request))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        try:
            guia = self._emit(request, tenant)
        except Exception as exc:
            messages.error(request, str(exc) or "Falha ao emitir guia.")
            return render(
                request,
                self.template_name,
                {**self._ctx(tenant, role, request), "form": request.POST},
            )
        messages.success(request, f"Guia {guia.tipo_guia} · {guia.competencia} disponível.")
        return redirect("hub-v4-das-detail", pk=guia.id)

    def _ctx(self, tenant, role, request):
        providers = Provider.objects.filter(tenant=tenant, is_active=True).order_by(
            "legal_name"
        )
        active = get_active_provider(request, tenant)
        today = date.today()
        # competência default = mês anterior
        if today.month == 1:
            comp = f"{today.year - 1}-12"
        else:
            comp = f"{today.year}-{today.month - 1:02d}"
        return {
            "nav": "das",
            "page_title": "Emitir guia DAS/DARF",
            "role_code": role,
            "providers": providers,
            "active_provider_id": str(active.id) if active else "",
            "tipos": GuiaFiscal.TipoGuia.choices,
            "idempotency_key": f"hub-das-{uuid.uuid4()}",
            "default_competencia": comp,
        }

    def _emit(self, request, tenant):
        from apps.accounts.exceptions import (
            CertificateNotUsableError,
            ElectronicProxyNotUsableError,
        )
        from apps.das.exceptions import DuplicateDasNaturalKeyError
        from apps.das.services import emitir_guia
        from integrations.receita.exceptions import (
            ReceitaAuthError,
            ReceitaBusinessError,
            ReceitaCredentialsMissingError,
            ReceitaHttpError,
            ReceitaHttpNotConfiguredError,
        )

        provider = get_object_or_404(
            Provider, pk=request.POST.get("provider_id"), tenant=tenant
        )
        tipo = (request.POST.get("tipo_guia") or GuiaFiscal.TipoGuia.DAS).strip()
        competencia = (request.POST.get("competencia") or "").strip()
        if not competencia:
            raise ValueError("Informe a competência (AAAA-MM).")
        try:
            return emitir_guia(
                tenant=tenant,
                idempotency_key=request.POST.get("idempotency_key")
                or f"hub-das-{uuid.uuid4()}",
                provider=provider,
                tipo_guia=tipo,
                competencia=competencia,
                versao_atual=int(request.POST.get("versao_atual") or "1"),
            )
        except (
            DuplicateDasNaturalKeyError,
            CertificateNotUsableError,
            ElectronicProxyNotUsableError,
            ReceitaHttpNotConfiguredError,
            ReceitaCredentialsMissingError,
            ReceitaAuthError,
            ReceitaHttpError,
            ReceitaBusinessError,
        ) as exc:
            raise ValueError(str(exc)) from exc


class DasDetailView(View):
    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        guia = get_object_or_404(
            GuiaFiscal.objects.select_related("provider"),
            pk=pk,
            tenant=tenant,
        )
        return render(
            request,
            "hub_v4/das/detail.html",
            {
                "nav": "das",
                "page_title": f"Guia {guia.tipo_guia}",
                "guia": guia,
                "role_code": role,
            },
        )


class CustomersListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        qs = Customer.objects.filter(tenant=tenant).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(document__icontains=q))
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/customers/list.html",
            {
                "nav": "customers",
                "page_title": "Clientes (tomadores)",
                "page": page,
                "q": q,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
            },
        )


class CustomerFormView(View):
    template_name = "hub_v4/customers/form.html"

    def get(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = get_object_or_404(Customer, pk=pk, tenant=tenant) if pk else None
        return render(
            request,
            self.template_name,
            {
                "nav": "customers",
                "page_title": "Editar tomador" if obj else "Novo tomador",
                "obj": obj,
                "role_code": role,
            },
        )

    def post(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = get_object_or_404(Customer, pk=pk, tenant=tenant) if pk else None
        try:
            saved = save_customer_from_post(tenant=tenant, post=request.POST, obj=obj)
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível salvar.")
            return render(
                request,
                self.template_name,
                {
                    "nav": "customers",
                    "page_title": "Editar tomador" if obj else "Novo tomador",
                    "obj": obj,
                    "role_code": role,
                    "form": request.POST,
                },
            )
        messages.success(
            request, "Tomador atualizado." if obj else "Tomador cadastrado."
        )
        return redirect("hub-v4-customer-edit", pk=saved.pk)


class ProvidersListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        qs = Provider.objects.filter(tenant=tenant).order_by("legal_name")
        if q:
            qs = qs.filter(
                Q(legal_name__icontains=q)
                | Q(trade_name__icontains=q)
                | Q(document__icontains=q)
            )
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        usage = provider_usage(tenant)
        return render(
            request,
            "hub_v4/providers/list.html",
            {
                "nav": "providers",
                "page_title": "Empresas (CNPJ)",
                "page": page,
                "q": q,
                "role_code": role,
                "usage": usage,
                "can_write": role in WRITE_ROLES,
                "can_add": role in WRITE_ROLES and not usage["at_limit"],
            },
        )


class ProviderFormView(View):
    template_name = "hub_v4/providers/form.html"

    def get(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = get_object_or_404(Provider, pk=pk, tenant=tenant) if pk else None
        usage = provider_usage(tenant)
        if obj is None and usage["at_limit"]:
            messages.error(
                request,
                f"Limite do plano atingido ({usage['label']} CNPJs ativos). "
                "Desative uma empresa ou solicite upgrade.",
            )
            return redirect("hub-v4-providers")
        return render(
            request,
            self.template_name,
            {
                "nav": "providers",
                "page_title": "Editar empresa" if obj else "Nova empresa",
                "obj": obj,
                "tax_regimes": TaxRegime.choices,
                "role_code": role,
                "usage": usage,
                "lookup_url": "hub-v4-provider-lookup",
            },
        )

    def post(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = get_object_or_404(Provider, pk=pk, tenant=tenant) if pk else None
        try:
            saved = save_provider_from_post(tenant=tenant, post=request.POST, obj=obj)
        except Exception as exc:
            messages.error(request, provider_form_error_message(exc))
            return render(
                request,
                self.template_name,
                {
                    "nav": "providers",
                    "page_title": "Editar empresa" if obj else "Nova empresa",
                    "obj": obj,
                    "tax_regimes": TaxRegime.choices,
                    "role_code": role,
                    "usage": provider_usage(tenant),
                    "form": request.POST,
                },
            )
        set_active_provider(request, tenant, str(saved.id))
        messages.success(
            request, "Empresa atualizada." if obj else "Empresa cadastrada."
        )
        return redirect("hub-v4-provider-edit", pk=saved.pk)


@require_http_methods(["POST"])
def set_active_company(request: HttpRequest):
    tenant, user, role, redir = require_hub(request)
    if redir:
        return redir
    provider_id = (request.POST.get("provider_id") or "").strip()
    provider = set_active_provider(request, tenant, provider_id)
    if provider is None:
        messages.error(request, "Empresa inválida ou inativa.")
    else:
        messages.success(
            request,
            f"Empresa ativa: {provider.legal_name}.",
        )
    next_url = (request.POST.get("next") or "").strip() or request.META.get(
        "HTTP_REFERER", ""
    )
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("hub-v4-providers")


@require_http_methods(["GET", "POST"])
def provider_lookup_document(request: HttpRequest):
    """Lookup CNPJ para formulário de Empresa (sessão Hub, sem JWT)."""
    tenant, user, role, redir = require_hub(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Não autenticado"}, status=401)
    if role not in WRITE_ROLES:
        return JsonResponse({"ok": False, "error": "Sem permissão"}, status=403)

    if request.method == "POST" and request.content_type and "json" in request.content_type:
        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            body = {}
        raw = body.get("document") or ""
        force = bool(body.get("force"))
    else:
        raw = request.GET.get("document") or request.POST.get("document") or ""
        force = (request.GET.get("force") or request.POST.get("force") or "") in {
            "1",
            "true",
            "yes",
        }
    doc = "".join(ch for ch in raw if ch.isdigit())
    try:
        data = lookup_document(
            tenant=tenant,
            document=doc,
            entity_kind="provider",
            force=force,
        )
        addr = data.address.as_dict() if hasattr(data.address, "as_dict") else {}
        return JsonResponse(
            {
                "ok": True,
                "document": data.document,
                "legal_name": data.legal_name,
                "trade_name": data.trade_name or "",
                "situacao_cadastral": data.situacao_cadastral or "",
                "data_abertura": str(data.data_abertura or ""),
                "natureza_juridica": data.natureza_juridica or "",
                "cnae_principal": data.cnae_principal or "",
                "porte": data.porte or "",
                "telefone": data.telefone or "",
                "email": data.email or "",
                "address": addr,
                "data_source": "receita",
                "raw": data.raw if isinstance(data.raw, dict) else {},
                "cached": bool(getattr(data, "cached", False)),
            }
        )
    except (
        CadastroCpfLookupNotSupportedError,
        CadastroDocumentInvalidError,
        CadastroNotFoundError,
        CadastroProviderUnavailableError,
    ) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


def _require_nfe_hub(request: HttpRequest, *, write: bool = False):
    if write:
        tenant, user, role, redir = _require_writer_hub(request)
    else:
        tenant, user, role, redir = require_hub(request)
    if redir:
        return tenant, user, role, redir
    if not nfe_enabled_for_tenant(tenant):
        messages.warning(
            request,
            "NF-e não está habilitada para este tenant. Solicite liberação à plataforma.",
        )
        return tenant, user, role, redirect("hub-v4-dashboard")
    return tenant, user, role, None


class NfeListView(View):
    """NF-e (modelo 55) — visível só com NFE_ENABLED + tenant.settings.nfe_enabled."""

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        status = (request.GET.get("status") or "all").strip()
        qs = NfeInvoice.objects.filter(tenant=tenant).select_related(
            "customer", "provider"
        )
        qs = filter_invoice_queryset(
            qs, status=status, q=q or None, apply_default_period=False
        ).order_by("-created_at")
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/nfe/list.html",
            {
                "nav": "nfe",
                "page_title": "NF-e",
                "page": page,
                "q": q,
                "status": status,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
                "nfe_http_mode": getattr(dj_settings, "NFE_HTTP_MODE", "stub"),
                "nfe_tp_amb": getattr(dj_settings, "NFE_DEFAULT_TP_AMB", "2"),
            },
        )


class NfeEmitView(View):
    """Cria draft + 1 item + emit (stub SEFAZ em lab)."""

    template_name = "hub_v4/nfe/form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_hub(request, write=True)
        if redir:
            return redir
        return render(request, self.template_name, self._ctx(tenant, role, request))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_hub(request, write=True)
        if redir:
            return redir
        try:
            inv = self._emit_from_post(request, tenant, actor=user.email or "hub")
        except Exception as exc:
            messages.error(request, str(exc) or "Falha ao emitir NF-e.")
            return render(
                request,
                self.template_name,
                {**self._ctx(tenant, role, request), "form": request.POST},
            )
        messages.success(
            request,
            f"NF-e {inv.get_status_display()} · série {inv.series}"
            + (f" nº {inv.number}" if inv.number else "")
            + ".",
        )
        return redirect("hub-v4-nfe-detail", pk=inv.id)

    def _ctx(self, tenant, role, request):
        providers = list(
            Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
        )
        customers = list(
            Customer.objects.filter(tenant=tenant, is_active=True).order_by("name")[:300]
        )
        products = list(
            NfeProduct.objects.filter(tenant=tenant, is_active=True).order_by("code")[
                :200
            ]
        )
        active = get_active_provider(request, tenant)
        return {
            "nav": "nfe",
            "page_title": "Emitir NF-e",
            "role_code": role,
            "providers": providers,
            "customers": customers,
            "products": products,
            "active_provider_id": str(active.id) if active else "",
            "idempotency_key": f"hub-nfe-{uuid.uuid4()}",
            "default_tp_amb": getattr(dj_settings, "NFE_DEFAULT_TP_AMB", "2") or "2",
            "nfe_http_mode": getattr(dj_settings, "NFE_HTTP_MODE", "stub"),
            "today": date.today().isoformat(),
        }

    def _emit_from_post(self, request, tenant, *, actor: str) -> NfeInvoice:
        from apps.nfe.exceptions import (
            NfeDisabledError,
            NfeGateError,
            NfeInvalidTransitionError,
            NfeValidationError,
            NfeVersionConflictError,
        )

        provider = get_object_or_404(
            Provider, pk=request.POST.get("provider_id"), tenant=tenant
        )
        customer = get_object_or_404(
            Customer, pk=request.POST.get("customer_id"), tenant=tenant
        )
        series = int(request.POST.get("series") or "1")
        tp_amb = (request.POST.get("tp_amb") or "").strip() or None
        nature = (request.POST.get("nature_operation") or "VENDA").strip() or "VENDA"
        issue = request.POST.get("issue_date") or date.today().isoformat()
        product_id = (request.POST.get("product_id") or "").strip()

        item: dict = {}
        if product_id:
            product = get_object_or_404(NfeProduct, pk=product_id, tenant=tenant)
            item["product_id"] = str(product.id)
            qty = (request.POST.get("quantity") or "1").strip() or "1"
            item["quantity"] = qty
            raw_price = (request.POST.get("unit_price") or "").strip()
            if raw_price:
                if "," in raw_price:
                    raw_price = raw_price.replace(".", "").replace(",", ".")
                try:
                    item["unit_price_cents"] = int(
                        (Decimal(raw_price) * 100).quantize(Decimal("1"))
                    )
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError("Preço unitário inválido") from exc
        else:
            code = (request.POST.get("item_code") or "ITEM1").strip()[:60]
            description = (request.POST.get("item_description") or code).strip()[:120]
            ncm = "".join(ch for ch in (request.POST.get("item_ncm") or "") if ch.isdigit())[
                :8
            ]
            if len(ncm) != 8:
                raise ValueError("NCM com 8 dígitos é obrigatório (sem produto do catálogo).")
            raw_price = (request.POST.get("unit_price") or "0").strip()
            if "," in raw_price:
                raw_price = raw_price.replace(".", "").replace(",", ".")
            try:
                unit_cents = int((Decimal(raw_price) * 100).quantize(Decimal("1")))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("Preço unitário inválido") from exc
            if unit_cents < 1:
                raise ValueError("Preço unitário deve ser positivo.")
            qty = (request.POST.get("quantity") or "1").strip() or "1"
            item = {
                "code": code,
                "description": description,
                "ncm": ncm,
                "quantity": qty,
                "unit_price_cents": unit_cents,
                "csosn": (request.POST.get("csosn") or "102").strip()[:3],
                "cfop": (request.POST.get("cfop") or "").strip()[:4] or None,
            }
            if not item["cfop"]:
                item.pop("cfop", None)

        try:
            inv = create_draft(
                tenant=tenant,
                provider=provider,
                customer=customer,
                idempotency_key=request.POST.get("idempotency_key")
                or f"hub-nfe-{uuid.uuid4()}",
                nature_operation=nature,
                series=max(1, series),
                tp_amb=tp_amb,
                ind_ie_dest=(request.POST.get("ind_ie_dest") or "9").strip() or "9",
                issue_date=date.fromisoformat(issue),
                actor=actor,
            )
            replace_items(inv, items=[item])
            return emit_invoice(inv, actor=actor)
        except (
            NfeDisabledError,
            NfeGateError,
            NfeInvalidTransitionError,
            NfeValidationError,
            NfeVersionConflictError,
        ) as exc:
            detail = str(exc)
            # API dumps field_errors as JSON string no validation
            if detail.startswith("{"):
                raise ValueError(f"Validação NF-e: {detail}") from exc
            raise ValueError(detail) from exc


class NfeDetailView(View):
    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_nfe_hub(request)
        if redir:
            return redir
        inv = get_object_or_404(
            NfeInvoice.objects.select_related("customer", "provider").prefetch_related(
                "items"
            ),
            pk=pk,
            tenant=tenant,
        )
        acts = allowed_actions(inv)
        return render(
            request,
            "hub_v4/nfe/detail.html",
            {
                "nav": "nfe",
                "page_title": f"NF-e · {inv.series}/{inv.number or '—'}",
                "invoice": inv,
                "items": list(inv.items.order_by("line_number")),
                "actions": acts,
                "can_cancel": "cancel" in acts and role in WRITE_ROLES,
                "can_cce": "cce" in acts and role in WRITE_ROLES,
                "docs": nfe_artifact_flags(inv),
                "role_code": role,
                "can_write": role in WRITE_ROLES,
            },
        )


class NfeCancelView(View):
    def post(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_nfe_hub(request, write=True)
        if redir:
            return redir
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=tenant)
        just = (request.POST.get("justificativa") or "").strip()
        try:
            from apps.nfe.exceptions import (
                NfeDisabledError,
                NfeInvalidTransitionError,
                NfeValidationError,
            )

            inv = cancel_invoice(
                inv,
                justificativa=just,
                actor=user.email or "hub",
            )
        except (
            NfeDisabledError,
            NfeInvalidTransitionError,
            NfeValidationError,
            ValueError,
        ) as exc:
            messages.error(request, str(exc) or "Falha ao cancelar.")
            return redirect("hub-v4-nfe-detail", pk=pk)
        if inv.status == NfeInvoice.Status.CANCELLED:
            messages.success(request, "NF-e cancelada na SEFAZ (ou stub).")
        else:
            messages.warning(
                request,
                inv.rejection_message
                or "Cancelamento não aceito — nota permanece autorizada.",
            )
        return redirect("hub-v4-nfe-detail", pk=inv.id)


class NfeCceView(View):
    def post(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_nfe_hub(request, write=True)
        if redir:
            return redir
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=tenant)
        corr = (request.POST.get("x_correcao") or "").strip()
        try:
            from apps.nfe.exceptions import (
                NfeDisabledError,
                NfeInvalidTransitionError,
                NfeValidationError,
            )

            inv = issue_carta_correcao(
                inv,
                x_correcao=corr,
                actor=user.email or "hub",
            )
        except (
            NfeDisabledError,
            NfeInvalidTransitionError,
            NfeValidationError,
            ValueError,
        ) as exc:
            messages.error(request, str(exc) or "Falha na CC-e.")
            return redirect("hub-v4-nfe-detail", pk=pk)
        messages.success(request, "Carta de Correção aceita.")
        return redirect("hub-v4-nfe-detail", pk=inv.id)


@require_http_methods(["GET"])
def nfe_document_download(request: HttpRequest, pk, kind: str):
    tenant, user, role, redir = _require_nfe_hub(request)
    if redir:
        return redir
    return download_nfe_artifact(tenant=tenant, invoice_id=pk, kind=kind)


class NfeProductsListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        qs = NfeProduct.objects.filter(tenant=tenant).order_by("code")
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(description__icontains=q) | Q(ncm__icontains=q))
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/nfe/products_list.html",
            {
                "nav": "nfe_products",
                "page_title": "Produtos NF-e",
                "page": page,
                "q": q,
                "count": qs.count(),
                "role_code": role,
                "can_write": role in WRITE_ROLES,
            },
        )


class NfeProductFormView(View):
    template_name = "hub_v4/nfe/product_form.html"

    def get(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_nfe_hub(request, write=True)
        if redir:
            return redir
        obj = None
        if pk:
            obj = get_object_or_404(NfeProduct, pk=pk, tenant=tenant)
        return render(
            request,
            self.template_name,
            self._ctx(tenant, role, obj=obj),
        )

    def post(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_nfe_hub(request, write=True)
        if redir:
            return redir
        obj = None
        if pk:
            obj = get_object_or_404(NfeProduct, pk=pk, tenant=tenant)
        try:
            saved = save_nfe_product_from_post(
                tenant=tenant, post=request.POST, obj=obj
            )
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível salvar o produto.")
            return render(
                request,
                self.template_name,
                {**self._ctx(tenant, role, obj=obj), "form": request.POST},
            )
        messages.success(request, f"Produto {saved.code} salvo.")
        return redirect("hub-v4-nfe-product-edit", pk=saved.pk)

    def _ctx(self, tenant, role, *, obj=None):
        unit_price_display = ""
        icms_display = ""
        pis_display = ""
        cofins_display = ""
        if obj:
            unit_price_display = f"{Decimal(obj.unit_price_cents) / Decimal(100):.2f}".replace(
                ".", ","
            )
            icms_display = f"{Decimal(obj.icms_rate_bp) / Decimal(100):.2f}".replace(
                ".", ","
            )
            pis_display = f"{Decimal(obj.pis_rate_bp) / Decimal(100):.2f}".replace(
                ".", ","
            )
            cofins_display = f"{Decimal(obj.cofins_rate_bp) / Decimal(100):.2f}".replace(
                ".", ","
            )
        return {
            "nav": "nfe_products",
            "page_title": "Editar produto" if obj else "Novo produto NF-e",
            "role_code": role,
            "obj": obj,
            "unit_price_display": unit_price_display,
            "icms_rate_display": icms_display,
            "pis_rate_display": pis_display,
            "cofins_rate_display": cofins_display,
        }


class CertificatesView(View):
    """Lista + upload A1 (multipart) no Hub, vinculado a empresa/CNPJ."""

    template_name = "hub_v4/certificates.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        return render(request, self.template_name, self._context(tenant, role, request))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir

        upload = request.FILES.get("file")
        label = (request.POST.get("label") or "A1").strip() or "A1"
        password = request.POST.get("password") or ""
        provider_id = (request.POST.get("provider_id") or "").strip()
        raw_cnpj = (request.POST.get("cnpj") or "").strip()
        make_primary = (request.POST.get("make_primary") or "1") in {
            "1",
            "true",
            "on",
            "yes",
        }

        provider = None
        if provider_id:
            provider = Provider.objects.filter(
                tenant=tenant, pk=provider_id, is_active=True
            ).first()
            if provider is None:
                messages.error(request, "Empresa inválida ou inativa.")
                return render(
                    request, self.template_name, self._context(tenant, role, request)
                )
            cnpj_digits = provider.document
        else:
            try:
                cnpj_digits = validate_cnpj(raw_cnpj)
            except ValueError as exc:
                messages.error(request, str(exc) or "CNPJ inválido.")
                return render(
                    request, self.template_name, self._context(tenant, role, request)
                )
            provider = Provider.objects.filter(
                tenant=tenant, document=cnpj_digits
            ).first()

        if not upload:
            messages.error(request, "Selecione o arquivo PFX/P12 do certificado A1.")
            return render(
                request, self.template_name, self._context(tenant, role, request)
            )

        pfx_bytes = upload.read()
        if not pfx_bytes:
            messages.error(request, "Arquivo de certificado vazio.")
            return render(
                request, self.template_name, self._context(tenant, role, request)
            )

        try:
            cert = upload_a1_certificate(
                tenant=tenant,
                label=label,
                cnpj=cnpj_digits,
                pfx_bytes=pfx_bytes,
                password=password,
                provider=provider,
                actor_user=user,
                make_primary=make_primary,
            )
        except PfxParseError as exc:
            messages.error(request, str(exc) or "PFX inválido ou senha incorreta.")
            return render(
                request, self.template_name, self._context(tenant, role, request)
            )
        except CryptoError as exc:
            messages.error(request, str(exc) or "Erro de criptografia do storage.")
            return render(
                request, self.template_name, self._context(tenant, role, request)
            )
        except Exception as exc:  # unique thumbprint etc.
            messages.error(request, str(exc) or "Não foi possível enviar o certificado.")
            return render(
                request, self.template_name, self._context(tenant, role, request)
            )

        if provider is not None:
            set_active_provider(request, tenant, str(provider.id))
        messages.success(
            request,
            f"Certificado «{cert.label}» enviado para CNPJ {cert.cnpj}"
            + (" (principal)." if cert.is_primary else "."),
        )
        return redirect("hub-v4-certificates")

    def _context(self, tenant, role, request):
        providers = list(
            Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
        )
        active = get_active_provider(request, tenant)
        preferred = (request.GET.get("empresa") or "").strip()
        active_id = preferred or (str(active.id) if active else "")
        if preferred and not any(str(p.id) == preferred for p in providers):
            active_id = str(active.id) if active else ""
        return {
            "nav": "certificates",
            "page_title": "Certificados",
            "rows": certificate_rows(tenant),
            "role_code": role,
            "can_write": role in WRITE_ROLES,
            "providers": providers,
            "active_provider_id": active_id,
        }


class FiscalProfilesListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        qs = FiscalProfile.objects.filter(tenant=tenant).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(tax_regime__icontains=q))
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/fiscal/list.html",
            {
                "nav": "fiscal",
                "page_title": "Perfis fiscais",
                "page": page,
                "q": q,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
            },
        )


class FiscalProfileFormView(View):
    template_name = "hub_v4/fiscal/form.html"

    def get(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = get_object_or_404(FiscalProfile, pk=pk, tenant=tenant) if pk else None
        return render(
            request,
            self.template_name,
            {
                "nav": "fiscal",
                "page_title": "Editar perfil fiscal" if obj else "Novo perfil fiscal",
                "obj": obj,
                "tax_regimes": TaxRegime.choices,
                "role_code": role,
                "services": ServiceCatalogItem.objects.filter(
                    tenant=tenant, is_active=True
                ).order_by("service_code")[:100],
            },
        )

    def post(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = get_object_or_404(FiscalProfile, pk=pk, tenant=tenant) if pk else None
        try:
            saved = save_fiscal_profile_from_post(
                tenant=tenant, post=request.POST, obj=obj
            )
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível salvar.")
            return render(
                request,
                self.template_name,
                {
                    "nav": "fiscal",
                    "page_title": "Editar perfil fiscal" if obj else "Novo perfil fiscal",
                    "obj": obj,
                    "tax_regimes": TaxRegime.choices,
                    "role_code": role,
                    "form": request.POST,
                    "services": ServiceCatalogItem.objects.filter(
                        tenant=tenant, is_active=True
                    ).order_by("service_code")[:100],
                },
            )
        messages.success(
            request,
            "Perfil fiscal atualizado."
            if obj
            else "Perfil fiscal cadastrado."
            + (
                " Regra municipal publicada."
                if (request.POST.get("ensure_rule") or "") in {"1", "true", "on", "yes"}
                else ""
            ),
        )
        return redirect("hub-v4-fiscal-edit", pk=saved.pk)


class TaxRulesListView(View):
    """Regras municipais do catálogo publicado do tenant."""

    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        published = TaxRuleCatalog.objects.filter(
            tenant=tenant, status=TaxRuleCatalog.Status.PUBLISHED
        ).first()
        qs = MunicipalTaxRule.objects.none()
        if published is not None:
            qs = (
                MunicipalTaxRule.objects.filter(catalog=published)
                .select_related("fiscal_profile")
                .order_by("ibge_code", "service_code", "fiscal_profile__name")
            )
            if q:
                qs = qs.filter(
                    Q(ibge_code__icontains=q)
                    | Q(municipio_nome__icontains=q)
                    | Q(service_code__icontains=q)
                    | Q(fiscal_profile__name__icontains=q)
                )
        page = Paginator(qs, 40).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/fiscal/rules_list.html",
            {
                "nav": "fiscal_rules",
                "page_title": "Regras municipais",
                "page": page,
                "q": q,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
                "published": published,
                "count": qs.count() if published else 0,
            },
        )


class FiscalReadinessView(View):
    """N1 — checklist go-live + matriz de cobertura ISS (ADR-FISCAL-001)."""

    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        from apps.fiscal.readiness import fiscal_readiness
        from apps.fiscal.templates_factory import list_templates

        readiness = fiscal_readiness(tenant=tenant)
        return render(
            request,
            "hub_v4/fiscal/readiness.html",
            {
                "nav": "fiscal_readiness",
                "page_title": "Pronto para emitir",
                "role_code": role,
                "can_write": role in WRITE_ROLES,
                "readiness": readiness,
                "templates": list_templates(),
                "profiles": FiscalProfile.objects.filter(tenant=tenant).order_by("name"),
            },
        )


class FiscalTemplateApplyView(View):
    """N2 — aplica template municipal linha a linha."""

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        from apps.fiscal.templates_factory import apply_template

        profile = FiscalProfile.objects.filter(
            tenant=tenant, pk=request.POST.get("fiscal_profile_id")
        ).first()
        if profile is None:
            messages.error(request, "Selecione um perfil fiscal.")
            return redirect("hub-v4-fiscal-readiness")
        codes = request.POST.getlist("service_codes")
        try:
            result = apply_template(
                tenant=tenant,
                profile=profile,
                template_id=(request.POST.get("template_id") or "").strip(),
                service_codes=codes or None,
            )
        except Exception as exc:
            messages.error(request, str(exc) or "Falha ao aplicar template.")
            return redirect("hub-v4-fiscal-readiness")
        messages.success(
            request,
            f"Template aplicado: {', '.join(result['applied_service_codes'])} "
            f"(catálogo v{result['catalog_version']}).",
        )
        return redirect("hub-v4-fiscal-readiness")


class FiscalCsvImportView(View):
    """N2 — import CSV de regras ISS."""

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        from apps.fiscal.templates_factory import import_rules_csv

        profile = FiscalProfile.objects.filter(
            tenant=tenant, pk=request.POST.get("fiscal_profile_id")
        ).first()
        if profile is None:
            messages.error(request, "Selecione um perfil fiscal.")
            return redirect("hub-v4-fiscal-readiness")
        upload = request.FILES.get("csv_file")
        raw = (request.POST.get("csv_text") or "").strip()
        if upload is not None:
            raw = upload.read().decode("utf-8-sig", errors="replace")
        try:
            result = import_rules_csv(tenant=tenant, profile=profile, csv_text=raw)
        except Exception as exc:
            messages.error(request, str(exc) or "Falha no import CSV.")
            return redirect("hub-v4-fiscal-readiness")
        messages.success(
            request,
            f"CSV importado: {len(result['applied_service_codes'])} regra(s) "
            f"em {len(result.get('ibge_codes') or [])} município(s) "
            f"({', '.join(result.get('ibge_codes') or [])}) "
            f"(catálogo v{result['catalog_version']}).",
        )
        return redirect("hub-v4-fiscal-readiness")


class TaxRuleFormView(View):
    template_name = "hub_v4/fiscal/rules_form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        return render(
            request,
            self.template_name,
            self._ctx(tenant, role),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        try:
            catalog = save_tax_rule_from_post(tenant=tenant, post=request.POST)
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível publicar a regra.")
            return render(
                request,
                self.template_name,
                {**self._ctx(tenant, role), "form": request.POST},
            )
        messages.success(
            request,
            f"Regra municipal publicada (catálogo v{catalog.version}).",
        )
        return redirect("hub-v4-tax-rules")

    def _ctx(self, tenant, role):
        return {
            "nav": "fiscal_rules",
            "page_title": "Nova regra municipal",
            "role_code": role,
            "profiles": FiscalProfile.objects.filter(tenant=tenant).order_by("name"),
            "services": ServiceCatalogItem.objects.filter(
                tenant=tenant, is_active=True
            ).order_by("service_code")[:200],
        }


class ServicesListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        qs = ServiceCatalogItem.objects.filter(tenant=tenant).order_by("service_code")
        if q:
            qs = qs.filter(
                Q(service_code__icontains=q)
                | Q(description__icontains=q)
                | Q(lc116_item__icontains=q)
            )
        page = Paginator(qs, 40).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/services/list.html",
            {
                "nav": "services",
                "page_title": "Serviços",
                "page": page,
                "q": q,
                "role_code": role,
                "can_write": role in WRITE_ROLES,
                "count": qs.count(),
            },
        )


class ServiceFormView(View):
    template_name = "hub_v4/services/form.html"

    def get(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = (
            get_object_or_404(ServiceCatalogItem, pk=pk, tenant=tenant) if pk else None
        )
        return render(
            request,
            self.template_name,
            {
                "nav": "services",
                "page_title": "Editar serviço" if obj else "Novo serviço",
                "obj": obj,
                "role_code": role,
            },
        )

    def post(self, request: HttpRequest, pk=None):
        tenant, user, role, redir = _require_writer_hub(request)
        if redir:
            return redir
        obj = (
            get_object_or_404(ServiceCatalogItem, pk=pk, tenant=tenant) if pk else None
        )
        try:
            saved = save_service_from_post(tenant=tenant, post=request.POST, obj=obj)
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível salvar.")
            return render(
                request,
                self.template_name,
                {
                    "nav": "services",
                    "page_title": "Editar serviço" if obj else "Novo serviço",
                    "obj": obj,
                    "role_code": role,
                    "form": request.POST,
                },
            )
        messages.success(
            request, "Serviço atualizado." if obj else "Serviço cadastrado."
        )
        return redirect("hub-v4-service-edit", pk=saved.pk)


@require_http_methods(["POST"])
def services_materialize(request: HttpRequest):
    tenant, user, role, redir = _require_writer_hub(request)
    if redir:
        return redir
    from apps.master_data.national_service_import import (
        NationalServiceImportError,
        materialize_national_services_for_tenant,
    )
    from apps.master_data.services import ensure_services_for_wizard

    try:
        result = materialize_national_services_for_tenant(
            tenant=tenant, only_missing=True
        )
        created = int((result or {}).get("created") or 0)
        messages.success(
            request,
            f"Lista nacional materializada: {created} serviço(s) novo(s)."
            if created
            else "Lista nacional já estava materializada neste tenant.",
        )
    except NationalServiceImportError:
        ensure_services_for_wizard(tenant=tenant)
        messages.info(
            request,
            "Lista nacional publicada indisponível — catálogo mínimo semeado para o wizard.",
        )
    return redirect("hub-v4-services")


class IntegrationsView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        return render(
            request,
            "hub_v4/integrations.html",
            {
                "nav": "integrations",
                "page_title": "Integrações",
                "role_code": role,
                "payment_provider": (tenant.settings or {}).get("payment_provider")
                or "inter",
                "usage": provider_usage(tenant),
            },
        )


class UsersListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        qs = (
            TenantMembership.objects.filter(tenant=tenant)
            .select_related("user", "role")
            .order_by("-is_active", "user__name", "user__email")
        )
        if q:
            qs = qs.filter(
                Q(user__email__icontains=q)
                | Q(user__name__icontains=q)
                | Q(role__code__icontains=q)
            )
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        usage = provider_usage(tenant)
        can_admin = role in ADMIN_ROLES
        return render(
            request,
            "hub_v4/users/list.html",
            {
                "nav": "users",
                "page_title": "Usuários",
                "page": page,
                "q": q,
                "role_code": role,
                "can_admin": can_admin,
                "usage": usage,
                "can_add": can_admin and not usage["users"]["at_limit"],
            },
        )


class UserInviteView(View):
    template_name = "hub_v4/users/form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_tenant_admin_hub(request)
        if redir:
            return redir
        usage = provider_usage(tenant)
        if usage["users"]["at_limit"]:
            messages.error(
                request,
                f"Limite de usuários do plano ({usage['users']['label']}). "
                "Desative um vínculo ou solicite upgrade.",
            )
            return redirect("hub-v4-users")
        ensure_system_roles()
        return render(
            request,
            self.template_name,
            {
                "nav": "users",
                "page_title": "Convidar usuário",
                "role_code": role,
                "roles": TenantRole.objects.filter(
                    code__in=ASSIGNABLE_ROLE_CODES
                ).order_by("code"),
                "obj": None,
                "usage": usage,
            },
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_tenant_admin_hub(request)
        if redir:
            return redir
        try:
            mem, mem_created, user_created, plain_password = invite_or_link_user(
                tenant=tenant,
                email=request.POST.get("email") or "",
                name=request.POST.get("name") or "",
                password=request.POST.get("password") or "",
                role_code=request.POST.get("role_code") or "operator",
                is_active=(request.POST.get("is_active") or "1")
                in {"1", "true", "on", "yes"},
                generate_password_if_missing=True,
            )
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível convidar.")
            ensure_system_roles()
            return render(
                request,
                self.template_name,
                {
                    "nav": "users",
                    "page_title": "Convidar usuário",
                    "role_code": role,
                    "roles": TenantRole.objects.filter(
                        code__in=ASSIGNABLE_ROLE_CODES
                    ).order_by("code"),
                    "obj": None,
                    "form": request.POST,
                    "usage": provider_usage(tenant),
                },
            )
        if mem_created and user_created:
            msg = f"Usuário {mem.user.email} criado e vinculado."
        elif mem_created:
            msg = f"Usuário {mem.user.email} vinculado ao escritório."
        else:
            msg = f"Vínculo de {mem.user.email} atualizado."

        send_mail = (request.POST.get("send_invite_email") or "1") in {
            "1",
            "true",
            "on",
            "yes",
        }
        if send_mail:
            from apps.accounts.invite_email import send_tenant_invite_email

            login_url = request.build_absolute_uri(reverse("hub-v4-login"))
            try:
                send_tenant_invite_email(
                    tenant=tenant,
                    user=mem.user,
                    role_label=mem.role.name or mem.role.code,
                    hub_login_url=login_url,
                    temporary_password=plain_password if user_created else "",
                    actor_name=user.name or user.email,
                )
                msg += " E-mail de convite enviado."
            except Exception as exc:  # noqa: BLE001
                messages.warning(
                    request,
                    f"Usuário ok, mas o e-mail não saiu: {exc}. "
                    "Confira EMAIL_* no ambiente ou reenvie manualmente.",
                )
                messages.success(request, msg)
                return redirect("hub-v4-user-edit", pk=mem.pk)

        messages.success(request, msg)
        return redirect("hub-v4-user-edit", pk=mem.pk)


class UserEditView(View):
    template_name = "hub_v4/users/form.html"

    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_tenant_admin_hub(request)
        if redir:
            return redir
        mem = get_object_or_404(
            TenantMembership.objects.select_related("user", "role"),
            pk=pk,
            tenant=tenant,
        )
        ensure_system_roles()
        return render(
            request,
            self.template_name,
            {
                "nav": "users",
                "page_title": "Editar usuário",
                "role_code": role,
                "roles": TenantRole.objects.filter(
                    code__in=ASSIGNABLE_ROLE_CODES
                ).order_by("code"),
                "obj": mem,
                "usage": provider_usage(tenant),
            },
        )

    def post(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_tenant_admin_hub(request)
        if redir:
            return redir
        mem = get_object_or_404(
            TenantMembership.objects.select_related("user", "role"),
            pk=pk,
            tenant=tenant,
        )
        try:
            update_membership(
                membership=mem,
                role_code=request.POST.get("role_code") or mem.role.code,
                is_active=(request.POST.get("is_active") or "0")
                in {"1", "true", "on", "yes"},
                name=request.POST.get("name"),
                password=request.POST.get("password") or "",
                actor_user=user,
            )
        except Exception as exc:
            messages.error(request, str(exc) or "Não foi possível salvar.")
            ensure_system_roles()
            return render(
                request,
                self.template_name,
                {
                    "nav": "users",
                    "page_title": "Editar usuário",
                    "role_code": role,
                    "roles": TenantRole.objects.filter(
                        code__in=ASSIGNABLE_ROLE_CODES
                    ).order_by("code"),
                    "obj": mem,
                    "form": request.POST,
                    "usage": provider_usage(tenant),
                },
            )
        messages.success(request, "Usuário atualizado.")
        return redirect("hub-v4-user-edit", pk=mem.pk)


class PreferencesView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = require_hub(request)
        if redir:
            return redir
        return render(
            request,
            "hub_v4/preferences.html",
            {
                "nav": "preferences",
                "page_title": "Preferências",
                "role_code": role,
                "tenant": tenant,
                "user": user,
                "usage": provider_usage(tenant),
            },
        )
