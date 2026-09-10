from django import template

register = template.Library()


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
def status_badge(status):
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
    return {"tone": tone, "label": label}


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
