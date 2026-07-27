"""Telas Django de cadastro Prestador/Tomador (não Admin)."""

from __future__ import annotations

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_http_methods

from apps.accounts.auth_services import authenticate_for_tenant, issue_tokens
from apps.accounts.models import Tenant, User
from apps.accounts.permissions import WRITE_ROLES
from apps.master_data.models import Customer, DataSource, Provider, TaxRegime
from apps.master_data.services import create_customer, create_provider, lookup_document
from integrations.cadastro.exceptions import (
    CadastroCpfLookupNotSupportedError,
    CadastroDocumentInvalidError,
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)
from shared.exceptions import AuthenticationError
from shared.validators import validate_cnpj, validate_cpf

SESSION_TENANT = "cadastro_tenant_id"
SESSION_USER = "cadastro_user_id"
SESSION_ROLE = "cadastro_role_code"
SESSION_ACCESS = "cadastro_access_token"


def _session_ok(request: HttpRequest) -> bool:
    return bool(
        request.session.get(SESSION_TENANT)
        and request.session.get(SESSION_USER)
        and request.session.get(SESSION_ROLE) in WRITE_ROLES
    )


def _require_writer(request: HttpRequest):
    if not _session_ok(request):
        return None, None, redirect("cadastro-login")
    tenant = Tenant.objects.filter(pk=request.session[SESSION_TENANT]).first()
    user = User.objects.filter(pk=request.session[SESSION_USER]).first()
    if tenant is None or user is None:
        request.session.flush()
        return None, None, redirect("cadastro-login")
    return tenant, user, None


def _addr_from_post(post) -> dict:
    return {
        "logradouro": (post.get("logradouro") or "").strip(),
        "numero": (post.get("numero") or "").strip(),
        "complemento": (post.get("complemento") or "").strip(),
        "bairro": (post.get("bairro") or "").strip(),
        "cep": "".join(ch for ch in (post.get("cep") or "") if ch.isdigit())[:8],
        "municipio": (post.get("municipio") or "").strip(),
        "uf": (post.get("uf") or "").strip().upper()[:2],
        "codigo_municipio_ibge": (post.get("codigo_municipio_ibge") or "").strip(),
        "telefone": (post.get("telefone_receita") or "").strip(),
        "email": (post.get("email_receita") or "").strip(),
    }


def _cadastral_from_post(post) -> dict:
    data_abertura = (post.get("data_abertura") or "").strip() or None
    raw = post.get("receita_raw_payload") or ""
    payload = None
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"unparsed": raw[:2000]}
    source = (post.get("data_source") or DataSource.MANUAL).strip()
    if source not in {DataSource.MANUAL, DataSource.RECEITA}:
        source = DataSource.MANUAL
    out = {
        "situacao_cadastral": (post.get("situacao_cadastral") or "").strip(),
        "data_abertura": data_abertura,
        "cnae_principal": (post.get("cnae_principal") or "").strip(),
        "natureza_juridica": (post.get("natureza_juridica") or "").strip(),
        "porte": (post.get("porte") or "").strip(),
        "whatsapp": (post.get("whatsapp") or "").strip(),
        "contato_nome": (post.get("contato_nome") or "").strip(),
        "data_source": source,
        "receita_raw_payload": payload,
        "address": _addr_from_post(post),
    }
    if source == DataSource.RECEITA and payload:
        from django.utils import timezone

        out["last_lookup_at"] = timezone.now()
    return out



class CadastroLoginView(View):
    template_name = "master_data/login.html"

    def get(self, request):
        if _session_ok(request):
            return redirect("cadastro-home")
        return render(request, self.template_name)

    def post(self, request):
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
        if membership.role.code not in WRITE_ROLES:
            return render(
                request,
                self.template_name,
                {"error": "Seu papel não permite editar cadastros."},
            )
        tokens = issue_tokens(user=user, membership=membership)
        request.session[SESSION_TENANT] = str(membership.tenant_id)
        request.session[SESSION_USER] = str(user.id)
        request.session[SESSION_ROLE] = membership.role.code
        request.session[SESSION_ACCESS] = tokens["access"]
        request.session["cadastro_tenant_slug"] = membership.tenant.slug
        request.session["cadastro_tenant_name"] = membership.tenant.legal_name
        request.session["cadastro_user_name"] = user.name or user.email
        return redirect("cadastro-home")


@require_http_methods(["POST"])
def cadastro_logout(request):
    request.session.flush()
    return redirect("cadastro-login")


class CadastroHomeView(View):
    def get(self, request):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        return render(
            request,
            "master_data/home.html",
            {
                "tenant": tenant,
                "providers_count": Provider.objects.filter(tenant=tenant).count(),
                "customers_count": Customer.objects.filter(tenant=tenant).count(),
            },
        )


class ProviderListView(View):
    def get(self, request):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        items = Provider.objects.filter(tenant=tenant).order_by("legal_name")
        return render(
            request,
            "master_data/provider_list.html",
            {"tenant": tenant, "items": items},
        )


class ProviderFormView(View):
    template_name = "master_data/provider_form.html"

    def get(self, request, pk=None):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        obj = None
        if pk:
            obj = get_object_or_404(Provider, pk=pk, tenant=tenant)
        return render(
            request,
            self.template_name,
            {
                "tenant": tenant,
                "obj": obj,
                "tax_regimes": TaxRegime.choices,
                "access_token": request.session.get(SESSION_ACCESS, ""),
                "lookup_url": reverse("master-data-provider-lookup"),
            },
        )

    def post(self, request, pk=None):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        try:
            document = validate_cnpj(request.POST.get("document") or "")
        except ValueError as exc:
            messages.error(request, str(exc))
            return self.get(request, pk=pk)

        cadastral = _cadastral_from_post(request.POST)
        legal_name = (request.POST.get("legal_name") or "").strip()
        trade_name = (request.POST.get("trade_name") or "").strip()
        tax_regime = (request.POST.get("tax_regime") or TaxRegime.SIMPLES).strip()
        municipal = (request.POST.get("municipal_registration") or "").strip()
        if not legal_name:
            messages.error(request, "Informe a razão social.")
            return self.get(request, pk=pk)

        if pk:
            obj = get_object_or_404(Provider, pk=pk, tenant=tenant)
            obj.document = document
            obj.legal_name = legal_name
            obj.trade_name = trade_name
            obj.tax_regime = tax_regime
            obj.municipal_registration = municipal
            for key, value in cadastral.items():
                setattr(obj, key, value)
            if cadastral.get("data_source") == DataSource.RECEITA and obj.last_lookup_at is None:
                from django.utils import timezone

                obj.last_lookup_at = timezone.now()
            obj.save()
            messages.success(request, "Prestador atualizado.")
            return redirect("cadastro-provider-edit", pk=obj.pk)

        obj = create_provider(
            tenant=tenant,
            document=document,
            legal_name=legal_name,
            tax_regime=tax_regime,
            trade_name=trade_name,
            municipal_registration=municipal,
            **cadastral,
        )
        if obj.data_source == DataSource.RECEITA and obj.receita_raw_payload:
            from django.utils import timezone

            if obj.last_lookup_at is None:
                obj.last_lookup_at = timezone.now()
                obj.save(update_fields=["last_lookup_at"])
        messages.success(request, "Prestador cadastrado.")
        return redirect("cadastro-provider-edit", pk=obj.pk)


class CustomerListView(View):
    def get(self, request):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        items = Customer.objects.filter(tenant=tenant).order_by("name")
        return render(
            request,
            "master_data/customer_list.html",
            {"tenant": tenant, "items": items},
        )


class CustomerFormView(View):
    template_name = "master_data/customer_form.html"

    def get(self, request, pk=None):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        obj = None
        if pk:
            obj = get_object_or_404(Customer, pk=pk, tenant=tenant)
        return render(
            request,
            self.template_name,
            {
                "tenant": tenant,
                "obj": obj,
                "access_token": request.session.get(SESSION_ACCESS, ""),
                "lookup_url": reverse("master-data-customer-lookup"),
            },
        )

    def post(self, request, pk=None):
        tenant, _user, err = _require_writer(request)
        if err:
            return err
        document_type = (request.POST.get("document_type") or Customer.DocumentType.CNPJ).strip()
        raw_doc = request.POST.get("document") or ""
        try:
            if document_type == Customer.DocumentType.CPF:
                document = validate_cpf(raw_doc)
            else:
                document = validate_cnpj(raw_doc)
                document_type = Customer.DocumentType.CNPJ
        except ValueError as exc:
            messages.error(request, str(exc))
            return self.get(request, pk=pk)

        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        if not name:
            messages.error(request, "Informe o nome / razão social.")
            return self.get(request, pk=pk)

        cadastral = _cadastral_from_post(request.POST)
        if document_type == Customer.DocumentType.CPF:
            cadastral["data_source"] = DataSource.MANUAL
            cadastral["receita_raw_payload"] = None

        if pk:
            obj = get_object_or_404(Customer, pk=pk, tenant=tenant)
            obj.document = document
            obj.document_type = document_type
            obj.name = name
            obj.email = email
            for key, value in cadastral.items():
                setattr(obj, key, value)
            if cadastral.get("data_source") == DataSource.RECEITA and obj.last_lookup_at is None:
                from django.utils import timezone

                obj.last_lookup_at = timezone.now()
            obj.save()
            messages.success(request, "Tomador atualizado.")
            return redirect("cadastro-customer-edit", pk=obj.pk)

        obj = create_customer(
            tenant=tenant,
            document=document,
            document_type=document_type,
            name=name,
            email=email,
            **cadastral,
        )
        if obj.data_source == DataSource.RECEITA and obj.last_lookup_at is None:
            from django.utils import timezone

            obj.last_lookup_at = timezone.now()
            obj.save(update_fields=["last_lookup_at"])
        messages.success(request, "Tomador cadastrado.")
        return redirect("cadastro-customer-edit", pk=obj.pk)


@require_http_methods(["POST"])
def cadastro_lookup_ajax(request, entity_kind: str) -> HttpResponse:
    """Fallback JSON via sessão (mesmo contrato do endpoint API)."""
    tenant, _user, err = _require_writer(request)
    if err:
        return JsonResponse({"detail": "Não autenticado.", "code": "authentication_failed"}, status=401)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}
    try:
        result = lookup_document(
            tenant=tenant,
            document=str(body.get("document") or ""),
            entity_kind=entity_kind,
            force=bool(body.get("force")),
            persist_on_existing=bool(body.get("persist")),
        )
    except CadastroDocumentInvalidError as exc:
        return JsonResponse({"detail": str(exc), "code": exc.code}, status=400)
    except CadastroCpfLookupNotSupportedError as exc:
        return JsonResponse({"detail": str(exc), "code": exc.code}, status=400)
    except CadastroNotFoundError as exc:
        return JsonResponse({"detail": str(exc), "code": exc.code}, status=404)
    except CadastroProviderUnavailableError as exc:
        return JsonResponse({"detail": str(exc), "code": exc.code}, status=503)
    return JsonResponse(result.as_api_dict())
