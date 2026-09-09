"""Hub V4 — NF-e de entrada (Captura Fiscal)."""

from __future__ import annotations

from io import BytesIO

from django.conf import settings as dj_settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import FileResponse, HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.http import require_http_methods

from apps.accounts.exceptions import CertificateNotUsableError
from apps.accounts.permissions import WRITE_ROLES
from apps.hub_v4.active_company import get_active_provider
from apps.hub_v4.auth import require_hub
from apps.hub_v4.views import _require_writer_hub
from apps.master_data.models import Provider
from apps.nfe.entrada.artifacts import read_entrada_xml_bytes
from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.exceptions import ManifestationError, NfeEntradaDisabledError
from apps.nfe.entrada.feature import nfe_entrada_enabled_for_tenant
from apps.nfe.entrada.listing import compute_entrada_kpis, filter_entrada_queryset
from apps.nfe.entrada.models import NfeEntradaDocument, NfeEntradaManifestation
from apps.nfe.entrada.services.distribuicao import schedule_distribuicao_sync
from apps.nfe.entrada.services.manifestacao import manifest_entrada_document
from integrations.sefaz_nfe.manifestacao.evento import (
    TP_EVENTO_CIENCIA,
    TP_EVENTO_CONFIRMACAO,
    TP_EVENTO_DESCONHECIMENTO,
    TP_EVENTO_NAO_REALIZADA,
)
from shared.storage import StorageError


def _require_nfe_entrada_hub(request: HttpRequest, *, write: bool = False):
    if write:
        tenant, user, role, redir = _require_writer_hub(request)
    else:
        tenant, user, role, redir = require_hub(request)
    if redir:
        return tenant, user, role, redir
    if not nfe_entrada_enabled_for_tenant(tenant):
        messages.warning(
            request,
            "NF-e de entrada não está habilitada para este tenant.",
        )
        return tenant, user, role, redirect("hub-v4-dashboard")
    return tenant, user, role, None


def _base_ctx(*, tenant, role, request, nav="nfe_entrada"):
    active = get_active_provider(request, tenant)
    return {
        "nav": nav,
        "role_code": role,
        "can_write": role in WRITE_ROLES,
        "active_provider": active,
        "nfe_entrada_http_mode": getattr(dj_settings, "NFE_ENTRADA_HTTP_MODE", "stub"),
    }


class NfeEntradaListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_entrada_hub(request)
        if redir:
            return redir
        q = (request.GET.get("q") or "").strip()
        manifest_status = (request.GET.get("manifest_status") or "all").strip()
        xml_status = (request.GET.get("xml_status") or "all").strip()
        active = get_active_provider(request, tenant)
        provider_id = request.GET.get("provider_id") or (
            str(active.id) if active else ""
        )
        qs = NfeEntradaDocument.objects.filter(tenant=tenant).select_related(
            "provider", "stored_file"
        )
        qs = filter_entrada_queryset(
            qs,
            q=q or None,
            manifest_status=manifest_status,
            xml_status=xml_status,
            provider_id=provider_id or None,
            days=request.GET.get("days") or "0",
            apply_default_period=False,
        ).order_by("-issue_date", "-created_at")
        kpis = compute_entrada_kpis(qs)
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        cursor = None
        if active:
            cursor = get_or_create_cursor(tenant=tenant, provider=active)
        return render(
            request,
            "hub_v4/nfe/entrada/list.html",
            {
                **_base_ctx(tenant=tenant, role=role, request=request),
                "page_title": "NF-e de Entrada",
                "page": page,
                "q": q,
                "manifest_status": manifest_status,
                "xml_status": xml_status,
                "provider_id": provider_id,
                "kpis": kpis,
                "cursor": cursor,
                "providers": list(
                    Provider.objects.filter(tenant=tenant, is_active=True).order_by(
                        "legal_name"
                    )
                ),
            },
        )


class NfeEntradaDetailView(View):
    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_nfe_entrada_hub(request)
        if redir:
            return redir
        doc = get_object_or_404(
            NfeEntradaDocument.objects.select_related("provider", "stored_file").prefetch_related(
                "manifestations"
            ),
            pk=pk,
            tenant=tenant,
        )
        manifestations = list(doc.manifestations.order_by("-created_at"))
        accepted = {
            m.tp_evento
            for m in manifestations
            if m.status == NfeEntradaManifestation.Status.ACCEPTED
        }
        return render(
            request,
            "hub_v4/nfe/entrada/detail.html",
            {
                **_base_ctx(tenant=tenant, role=role, request=request),
                "page_title": f"NF-e entrada · {doc.series or '—'}/{doc.number or '—'}",
                "document": doc,
                "manifestations": manifestations,
                "can_ciencia": TP_EVENTO_CIENCIA not in accepted,
                "can_confirmacao": TP_EVENTO_CONFIRMACAO not in accepted,
                "can_desconhecimento": TP_EVENTO_DESCONHECIMENTO not in accepted,
                "can_nao_realizada": TP_EVENTO_NAO_REALIZADA not in accepted,
                "has_xml": bool(doc.stored_file_id),
            },
        )


class NfeEntradaConfigView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_entrada_hub(request)
        if redir:
            return redir
        active = get_active_provider(request, tenant)
        providers = list(
            Provider.objects.filter(tenant=tenant, is_active=True).order_by("legal_name")
        )
        pid = request.GET.get("provider_id") or (str(active.id) if active else "")
        cursor = None
        if pid:
            provider = get_object_or_404(Provider, pk=pid, tenant=tenant)
            cursor = get_or_create_cursor(tenant=tenant, provider=provider)
        return render(
            request,
            "hub_v4/nfe/entrada/config.html",
            {
                **_base_ctx(tenant=tenant, role=role, request=request),
                "page_title": "Configuração — NF-e de Entrada",
                "providers": providers,
                "provider_id": pid,
                "cursor": cursor,
            },
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_nfe_entrada_hub(request, write=True)
        if redir:
            return redir
        pid = (request.POST.get("provider_id") or "").strip()
        provider = get_object_or_404(Provider, pk=pid, tenant=tenant)
        cursor = get_or_create_cursor(tenant=tenant, provider=provider)
        cursor.automatic_enabled = request.POST.get("automatic_enabled") == "on"
        try:
            cursor.interval_seconds = max(
                300,
                int(request.POST.get("interval_seconds") or cursor.interval_seconds),
            )
        except (TypeError, ValueError):
            pass
        cursor.save(update_fields=["automatic_enabled", "interval_seconds", "updated_at"])
        messages.success(request, "Configuração de distribuição salva.")
        return redirect(f"{request.path}?provider_id={provider.id}")


@require_http_methods(["POST"])
def nfe_entrada_sync(request: HttpRequest):
    tenant, user, role, redir = _require_nfe_entrada_hub(request, write=True)
    if redir:
        return redir
    pid = (request.POST.get("provider_id") or "").strip()
    if pid:
        provider = get_object_or_404(Provider, pk=pid, tenant=tenant)
    else:
        provider = get_active_provider(request, tenant)
    if provider is None:
        messages.error(request, "Selecione uma empresa ativa.")
        return redirect("hub-v4-nfe-entrada-list")
    try:
        schedule_distribuicao_sync(tenant=tenant, provider=provider)
        messages.success(request, "Consulta de distribuição enfileirada.")
    except NfeEntradaDisabledError as exc:
        messages.error(request, str(exc))
    except CertificateNotUsableError as exc:
        messages.error(
            request,
            f"{exc}. Atualize o certificado A1 em Cadastro → Certificados.",
        )
    return redirect("hub-v4-nfe-entrada-list")


@require_http_methods(["POST"])
def nfe_entrada_manifest(request: HttpRequest, pk):
    tenant, user, role, redir = _require_nfe_entrada_hub(request, write=True)
    if redir:
        return redir
    doc = get_object_or_404(NfeEntradaDocument, pk=pk, tenant=tenant)
    tp_evento = (request.POST.get("tp_evento") or "").strip()
    confirmed = request.POST.get("confirmed") == "on"
    justificativa = (request.POST.get("justificativa") or "").strip() or None
    try:
        result = manifest_entrada_document(
            document=doc,
            tp_evento=tp_evento,
            actor_user=user,
            actor_ip=request.META.get("REMOTE_ADDR"),
            justificativa=justificativa,
            confirmed=confirmed,
        )
        if result.idempotent:
            messages.info(request, "Manifestação já registrada anteriormente.")
        else:
            messages.success(
                request,
                f"Manifestação homologada · protocolo {result.protocol or '—'}.",
            )
    except ManifestationError as exc:
        messages.error(request, str(exc))
    except NfeEntradaDisabledError as exc:
        messages.error(request, str(exc))
    except CertificateNotUsableError as exc:
        messages.error(
            request,
            f"{exc}. Atualize o certificado A1 em Cadastro → Certificados.",
        )
    return redirect("hub-v4-nfe-entrada-detail", pk=pk)


@require_http_methods(["GET"])
def nfe_entrada_xml_download(request: HttpRequest, pk):
    tenant, user, role, redir = _require_nfe_entrada_hub(request)
    if redir:
        return redir
    doc = get_object_or_404(
        NfeEntradaDocument.objects.select_related("stored_file"),
        pk=pk,
        tenant=tenant,
    )
    if doc.xml_status != NfeEntradaDocument.XmlStatus.AVAILABLE:
        messages.warning(request, "XML ainda não disponível para este documento.")
        return redirect("hub-v4-nfe-entrada-detail", pk=pk)
    try:
        data = read_entrada_xml_bytes(doc)
    except StorageError as exc:
        messages.error(request, str(exc))
        return redirect("hub-v4-nfe-entrada-detail", pk=pk)
    filename = f"entrada-{doc.access_key or doc.id}.xml"
    return FileResponse(
        BytesIO(data),
        as_attachment=True,
        filename=filename,
        content_type="application/xml",
    )
