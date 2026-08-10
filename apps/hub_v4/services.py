"""Agregações read-only do dashboard V4 (sem alterar regras fiscais)."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import DigitalCertificate
from apps.accounts.plan_limits import provider_usage
from apps.issuance.models import NfArtifact, NfIssue


def _usage_pct(block: dict) -> int | None:
    """Percentual 0–100 do teto; None se ilimitado ou sem base."""
    limit = block.get("limit")
    if limit is None or limit <= 0:
        return None
    used = int(block.get("used") or 0)
    return min(100, max(0, int(round(100 * used / limit))))


def dashboard_context(tenant) -> dict:
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

    certs = DigitalCertificate.objects.filter(tenant=tenant)
    cert_active = certs.filter(
        status__in=[
            DigitalCertificate.Status.ACTIVE,
            DigitalCertificate.Status.EXPIRING,
        ]
    ).count()
    expiring_soon = []
    for cert in certs.exclude(status=DigitalCertificate.Status.REVOKED):
        days = (cert.not_after.date() - today).days
        if days <= 30:
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
        {
            "key": "nf_month",
            "label": "NFS-e neste mês",
            "block": nf_u,
            "pct": _usage_pct(nf_u),
            "url_name": "hub-v4-nfse-list",
            "cta": "NFS-e",
        },
    ]

    pending_actions = []
    if rejected:
        pending_actions.append(
            {
                "tone": "danger",
                "title": f"{rejected} NFS-e rejeitada{'s' if rejected != 1 else ''}",
                "cta": "Resolver agora",
                "url_name": "hub-v4-nfse-list",
                "url_query": "status=rejected",
            }
        )
    if processing:
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
    if artifacts_pending:
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
    if nf_u.get("at_limit"):
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
    )

    return {
        "kpis": {
            "nfse_hoje": nfse_hoje,
            "processing": processing,
            "rejected": rejected,
            "cert_active": cert_active,
        },
        "usage": usage,
        "usage_rows": usage_rows,
        "pending_actions": pending_actions,
        "recent_issues": recent,
        "expiring_certs": expiring_soon[:5],
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


def certificate_rows(tenant):
    today = timezone.localdate()
    rows = []
    qs = (
        DigitalCertificate.objects.filter(tenant=tenant)
        .select_related("provider")
        .order_by("not_after")
    )
    for cert in qs:
        days = (cert.not_after.date() - today).days
        if days < 0:
            label = f"Expirado há {abs(days)} dias"
            sort_key = 3
        elif days <= 30:
            label = f"Expira em {days} dias"
            sort_key = 1
        else:
            label = "Ativo"
            sort_key = 2
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
