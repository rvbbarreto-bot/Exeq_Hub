"""Agregações read-only do dashboard V4 (sem alterar regras fiscais)."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.accounts.certificates import get_primary_certificate
from apps.accounts.models import DigitalCertificate
from apps.accounts.plan_limits import provider_usage
from apps.accounts.tenant_emission import nfse_enabled_for_tenant
from apps.issuance.models import NfArtifact, NfIssue

CERT_EXPIRING_DAYS = 30


def _cnpj_digits(cnpj: str | None) -> str:
    return "".join(ch for ch in (cnpj or "") if ch.isdigit())


def certificate_validity(*, today, not_after) -> tuple[int, str, str, int]:
    """days, label, tone (ok|warn|err), sort_key — alinhado à tela de certificados."""
    nd = not_after.date() if hasattr(not_after, "date") else not_after
    days = (nd - today).days
    if days < 0:
        return days, f"Expirado há {abs(days)} dias", "err", 3
    if days <= CERT_EXPIRING_DAYS:
        return days, f"Expira em {days} dias", "warn", 1
    return days, "Ativo", "ok", 2


def certificate_kpi(tenant, *, cnpj: str | None = None) -> dict:
    """KPI Certificados do dashboard — empresa em uso; sem A1 → 0 ativos."""
    if not _cnpj_digits(cnpj):
        return {
            "value": 0,
            "hint": "ativos",
            "tone": "total",
            "status": False,
            "days": None,
        }
    cert = get_primary_certificate(tenant=tenant, cnpj=cnpj)
    if cert is None:
        return {
            "value": 0,
            "hint": "ativos",
            "tone": "total",
            "status": False,
            "days": None,
        }
    today = timezone.localdate()
    days, label, tone, _ = certificate_validity(today=today, not_after=cert.not_after)
    return {
        "value": label,
        "hint": "",
        "tone": tone,
        "status": True,
        "days": days,
    }


def _usage_pct(block: dict) -> int | None:
    """Percentual 0–100 do teto; None se ilimitado ou sem base."""
    limit = block.get("limit")
    if limit is None or limit <= 0:
        return None
    used = int(block.get("used") or 0)
    return min(100, max(0, int(round(100 * used / limit))))


def dashboard_context(tenant, *, cnpj: str | None = None) -> dict:
    nfse_on = nfse_enabled_for_tenant(tenant)
    today = timezone.localdate()
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    base = NfIssue.objects.filter(tenant=tenant)
    nfse_hoje = base.filter(created_at__gte=start).count()
    processing = base.filter(
        status__in=[
            NfIssue.Status.QUEUED,
            NfIssue.Status.SUBMITTING,
            NfIssue.Status.POLLING,
            NfIssue.Status.PENDING_TAX,
        ]
    ).count()
    rejected = base.filter(status=NfIssue.Status.REJECTED).count()

    cert_kpi = certificate_kpi(tenant, cnpj=cnpj)
    certs = DigitalCertificate.objects.filter(tenant=tenant).exclude(
        status=DigitalCertificate.Status.REVOKED,
    )
    digits = _cnpj_digits(cnpj)
    if digits:
        certs = certs.filter(cnpj=digits)
    expiring_soon = []
    for cert in certs:
        days, _, _, _ = certificate_validity(today=today, not_after=cert.not_after)
        if days <= CERT_EXPIRING_DAYS:
            expiring_soon.append({"cert": cert, "days": days})
    expiring_soon.sort(key=lambda x: x["days"])

    authorized_ids = list(
        base.filter(status=NfIssue.Status.AUTHORIZED).values_list("id", flat=True)
    )
    with_pdf = set(
        NfArtifact.objects.filter(
            tenant=tenant,
            nf_issue_id__in=authorized_ids,
            kind=NfArtifact.Kind.PDF,
        ).values_list("nf_issue_id", flat=True)
    )
    artifacts_pending = len([i for i in authorized_ids if i not in with_pdf])

    usage = provider_usage(tenant)
    users_u = usage.get("users") or {}
    nf_u = usage.get("nf_month") or {}
    usage_rows = [
        {
            "key": "providers",
            "label": "CNPJs emitentes",
            "block": {
                "used": usage["used"],
                "limit": usage["limit"],
                "unlimited": usage["unlimited"],
                "remaining": usage["remaining"],
                "at_limit": usage["at_limit"],
                "label": usage["label"],
            },
            "pct": _usage_pct(usage),
            "url_name": "hub-v4-providers",
            "cta": "Empresas",
        },
        {
            "key": "users",
            "label": "Usuários ativos",
            "block": users_u,
            "pct": _usage_pct(users_u),
            "url_name": "hub-v4-users",
            "cta": "Usuários",
        },
    ]
    if nfse_on:
        usage_rows.append(
            {
                "key": "nf_month",
                "label": "NFS-e neste mês",
                "block": nf_u,
                "pct": _usage_pct(nf_u),
                "url_name": "hub-v4-nfse-list",
                "cta": "NFS-e",
            }
        )

    pending_actions = []
    if nfse_on and rejected:
        pending_actions.append(
            {
                "tone": "danger",
                "title": f"{rejected} NFS-e rejeitada{'s' if rejected != 1 else ''}",
                "cta": "Resolver agora",
                "url_name": "hub-v4-nfse-list",
                "url_query": "status=rejected",
            }
        )
    if nfse_on and processing:
        pending_actions.append(
            {
                "tone": "warning",
                "title": f"{processing} em processamento",
                "cta": "Acompanhar",
                "url_name": "hub-v4-nfse-list",
                "url_query": "status=processing",
            }
        )
    if expiring_soon:
        d0 = expiring_soon[0]["days"]
        n = len(expiring_soon)
        pending_actions.append(
            {
                "tone": "amber",
                "title": f"{n} certificado(s) expirando (ex.: {d0}d)",
                "cta": "Ver certificados",
                "url_name": "hub-v4-certificates",
                "url_query": "",
            }
        )
    if nfse_on and artifacts_pending:
        pending_actions.append(
            {
                "tone": "info",
                "title": f"{artifacts_pending} documento(s) PDF pendente(s)",
                "cta": "Ver autorizadas",
                "url_name": "hub-v4-nfse-list",
                "url_query": "status=authorized",
            }
        )
    if usage.get("at_limit"):
        pending_actions.append(
            {
                "tone": "warning",
                "title": f"Limite de CNPJs do plano ({usage['label']})",
                "cta": "Gerenciar empresas",
                "url_name": "hub-v4-providers",
                "url_query": "",
            }
        )
    if users_u.get("at_limit"):
        pending_actions.append(
            {
                "tone": "warning",
                "title": f"Limite de usuários do plano ({users_u['label']})",
                "cta": "Gerenciar usuários",
                "url_name": "hub-v4-users",
                "url_query": "",
            }
        )
    if nfse_on and nf_u.get("at_limit"):
        pending_actions.append(
            {
                "tone": "warning",
                "title": f"Limite mensal de NFS-e ({nf_u['label']})",
                "cta": "Ver emissões",
                "url_name": "hub-v4-nfse-list",
                "url_query": "",
            }
        )

    recent = (
        base.select_related("customer", "provider", "service")
        .order_by("-created_at")[:12]
        if nfse_on
        else NfIssue.objects.none()
    )

    return {
        "kpis": {
            "nfse_hoje": nfse_hoje if nfse_on else 0,
            "processing": processing if nfse_on else 0,
            "rejected": rejected if nfse_on else 0,
            "cert": cert_kpi,
        },
        "usage": usage,
        "usage_rows": usage_rows,
        "pending_actions": pending_actions,
        "recent_issues": recent,
        "expiring_certs": expiring_soon[:5],
        "nfse_enabled": nfse_on,
    }


def nfse_queryset(tenant, *, status: str = "", q: str = ""):
    qs = (
        NfIssue.objects.filter(tenant=tenant)
        .select_related("customer", "provider", "service")
        .order_by("-created_at")
    )
    st = (status or "").strip().lower()
    if st == "processing":
        qs = qs.filter(
            status__in=[
                NfIssue.Status.QUEUED,
                NfIssue.Status.SUBMITTING,
                NfIssue.Status.POLLING,
                NfIssue.Status.PENDING_TAX,
                NfIssue.Status.DRAFT,
            ]
        )
    elif st and st != "all":
        qs = qs.filter(status=st)
    qv = (q or "").strip()
    if qv:
        qs = qs.filter(
            Q(customer__name__icontains=qv)
            | Q(focus_ref__icontains=qv)
            | Q(rejection_code__icontains=qv)
            | Q(service__description__icontains=qv)
        )
    return qs


def certificate_rows(tenant, *, cnpj: str | None = None):
    """Certificados do tenant; se cnpj informado, só da empresa em uso."""
    today = timezone.localdate()
    rows = []
    qs = DigitalCertificate.objects.filter(tenant=tenant).select_related("provider")
    if cnpj:
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        if digits:
            qs = qs.filter(cnpj=digits)
    qs = qs.order_by("not_after")
    for cert in qs:
        days, label, _, sort_key = certificate_validity(
            today=today, not_after=cert.not_after
        )
        provider_name = ""
        if cert.provider_id:
            provider_name = cert.provider.trade_name or cert.provider.legal_name
        rows.append(
            {
                "cert": cert,
                "days": days,
                "label": label,
                "sort_key": sort_key,
                "provider_name": provider_name,
            }
        )
    rows.sort(key=lambda r: (r["sort_key"], r["days"] if r["days"] is not None else 9999))
    return rows


def issue_timeline(issue: NfIssue) -> list[dict]:
    """Timeline fiscal UI a partir de status/eventos (apresentação)."""
    steps = [
        ("draft", "Rascunho"),
        ("pending_tax", "Tributação"),
        ("queued", "Na fila"),
        ("submitting", "DPS enviada"),
        ("polling", "Processando"),
        ("authorized", "Autorizada"),
        ("rejected", "Rejeitada"),
        ("cancelled", "Cancelada"),
        ("failed", "Falhou"),
    ]
    order = {s: i for i, (s, _) in enumerate(steps)}
    cur = order.get(issue.status, 0)
    out = []
    # Linear happy-path markers for authorized flow
    happy = ["draft", "pending_tax", "queued", "submitting", "polling", "authorized"]
    if issue.status == NfIssue.Status.REJECTED:
        happy = ["draft", "pending_tax", "queued", "submitting", "polling", "rejected"]
    elif issue.status == NfIssue.Status.CANCELLED:
        happy = ["draft", "pending_tax", "queued", "submitting", "polling", "authorized", "cancelled"]
    elif issue.status == NfIssue.Status.FAILED:
        happy = ["draft", "pending_tax", "failed"]

    reached = False
    for code, label in steps:
        if code not in happy and code != issue.status:
            continue
        idx = happy.index(code) if code in happy else -1
        cur_idx = happy.index(issue.status) if issue.status in happy else -1
        done = idx >= 0 and cur_idx >= 0 and idx <= cur_idx
        out.append({"code": code, "label": label, "done": done, "current": code == issue.status})
    # document flags
    arts = list(issue.artifacts.all()) if issue.pk else []
    kinds = {a.kind for a in arts}
    out.append(
        {
            "code": "danfse",
            "label": "DANFSE",
            "done": NfArtifact.Kind.PDF in kinds or "pdf" in kinds,
            "current": False,
        }
    )
    out.append(
        {
            "code": "xml",
            "label": "XML armazenado",
            "done": NfArtifact.Kind.XML in kinds or "xml" in kinds,
            "current": False,
        }
    )
    return out


def hub_nbs_catalog() -> list[dict]:
    from apps.master_data.nbs_import import list_published_nbs_catalog

    return list_published_nbs_catalog()
