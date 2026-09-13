from django import template

from integrations.sefaz_nfe.distribuicao import CSTAT_NENHUM_DOCUMENTO

register = template.Library()


@register.filter
def nfce_rejection_display(invoice) -> str:
    """Mensagem de rejeição/falha NFC-e amigável (inclui registros legados técnicos)."""
    from apps.nfce.user_messages import format_nfce_rejection_message

    if invoice is None:
        return ""
    return format_nfce_rejection_message(
        getattr(invoice, "rejection_code", None),
        getattr(invoice, "rejection_message", None),
    )


@register.filter
def entrada_last_cstat_display(cursor) -> str:
    """Último cStat para UI — omite código 137 (fila vazia, sem documentos)."""
    if cursor is None:
        return "—"
    c_stat = (getattr(cursor, "last_c_stat", None) or "").strip()
    motivo = (getattr(cursor, "last_x_motivo", None) or "").strip()
    if c_stat == CSTAT_NENHUM_DOCUMENTO:
        return motivo or "Nenhum documento localizado"
    if c_stat:
        return f"{c_stat} {motivo}".strip()
    return motivo or "—"


@register.inclusion_tag("hub_v4/components/kpi_card.html")
def kpi_card(label, value, hint="", tone="total", status=False):
    return {
        "label": label,
        "value": value,
        "hint": hint,
        "tone": tone,
        "status": status,
    }


@register.inclusion_tag("hub_v4/components/status_badge.html")
def import_status_badge(status):
    s = (status or "").upper()
    mapping = {
        "NOVO": ("success", "Novo"),
        "ATUALIZAÇÃO": ("warning", "Atualização"),
        "SEM ALTERAÇÃO": ("neutral", "Sem alteração"),
        "ERRO": ("danger", "Erro"),
        "NÃO PROCESSADO": ("danger", "Não processado"),
        "PROCESSADO": ("success", "Processado"),
    }
    tone, label = mapping.get(s, ("neutral", status or "—"))
    return {"tone": tone, "label": label}


@register.inclusion_tag("hub_v4/components/status_badge.html")
def status_badge(status, tooltip=""):
    s = (status or "").lower()
    mapping = {
        "authorized": ("success", "Autorizada"),
        "rejected": ("danger", "Rejeitada"),
        "cancelled": ("neutral", "Cancelada"),
        "cancel_requested": ("warning", "Cancelamento pendente"),
        "failed": ("danger", "Falhou"),
        "registered": ("success", "Registrada"),
        "pending": ("warning", "Pendente"),
        "draft": ("neutral", "Rascunho"),
        "queued": ("warning", "Na fila"),
        "submitting": ("warning", "Enviando"),
        "polling": ("warning", "Processando"),
        "pending_tax": ("warning", "Tributação"),
        "open": ("warning", "Aberta"),
        "paid": ("success", "Paga"),
        "overdue": ("danger", "Vencida"),
        "active": ("success", "Ativo"),
        "inactive": ("neutral", "Inativo"),
        "accepted": ("success", "Homologado"),
        "rejected": ("danger", "Rejeitado"),
        "expired": ("danger", "Expirado"),
        "expiring": ("warning", "A expirar"),
    }
    tone, label = mapping.get(s, ("neutral", status or "—"))
    return {"tone": tone, "label": label}


@register.inclusion_tag("hub_v4/components/status_badge.html")
def entrada_manifest_badge(status):
    s = (status or "").lower()
    mapping = {
        "none": ("warning", "Sem manifestação"),
        "ciencia": ("neutral", "Ciência"),
        "confirmada": ("success", "Confirmada"),
        "desconhecida": ("skip", "Desconhecida"),
        "nao_realizada": ("danger", "Não realizada"),
    }
    tone, label = mapping.get(s, ("neutral", status or "—"))
    return {"tone": tone, "label": label, "tooltip": ""}


@register.inclusion_tag("hub_v4/components/status_badge.html")
def guia_status_badge(status):
    s = (status or "").upper()
    mapping = {
        "PROCESSANDO": ("warning", "Processando"),
        "DISPONIVEL": ("success", "Disponível"),
        "PAGO": ("success", "Pago"),
        "CANCELADO": ("neutral", "Cancelado"),
        "RETIFICADO": ("warning", "Retificado"),
        "VENCIDO": ("danger", "Vencido"),
        "EM_CONTESTACAO": ("warning", "Em contestação"),
    }
    tone, label = mapping.get(s, ("neutral", status or "—"))
    return {"tone": tone, "label": label}


@register.inclusion_tag("hub_v4/components/status_badge.html")
def guia_compliance_badge(status):
    s = (status or "").lower()
    mapping = {
        "pendente": ("warning", "Pendente"),
        "aprovado": ("success", "Aprovado"),
        "bloqueado": ("danger", "Bloqueado"),
        "dispensado": ("neutral", "Dispensado"),
    }
    tone, label = mapping.get(s, ("neutral", status or "—"))
    return {"tone": tone, "label": label}


@register.inclusion_tag("hub_v4/components/status_badge.html")
def delivery_channel_badge(sent):
    if sent:
        return {"tone": "success", "label": "Enviado"}
    return {"tone": "warning", "label": "Pendente"}


@register.inclusion_tag("hub_v4/components/status_badge.html")
def entrada_xml_badge(status):
    s = (status or "").lower()
    mapping = {
        "pending": ("warning", "XML pendente"),
        "available": ("success", "XML disponível"),
        "error": ("danger", "Erro XML"),
    }
    tone, label = mapping.get(s, ("neutral", status or "—"))
    return {"tone": tone, "label": label}


@register.inclusion_tag("hub_v4/components/empty_state.html")
def empty_state(title, description="", cta_label="", cta_url=""):
    return {
        "title": title,
        "description": description,
        "cta_label": cta_label,
        "cta_url": cta_url,
    }


@register.inclusion_tag("hub_v4/components/pending_action_card.html")
def pending_action_card(action):
    return {"action": action}


@register.filter
def cents_brl(value):
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return "—"
    reais = cents / 100.0
    formatted = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


_MONTHS_PT = (
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
)


@register.filter
def mes_label(value):
    try:
        year = value[:4]
        month = int(value[5:7])
        return f"{_MONTHS_PT[month - 1]}/{year}"
    except (IndexError, ValueError, TypeError):
        return value or "—"


@register.inclusion_tag("hub_v4/components/status_badge.html")
def consumption_badge(billable, outcome):
    if billable:
        return {"tone": "success", "label": "Faturável"}
    if (outcome or "").lower() == "failure":
        return {"tone": "danger", "label": "Falha"}
    return {"tone": "neutral", "label": "Não faturável"}
