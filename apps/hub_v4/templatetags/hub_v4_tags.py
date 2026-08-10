from django import template

register = template.Library()


@register.inclusion_tag("hub_v4/components/kpi_card.html")
def kpi_card(label, value, hint=""):
    return {"label": label, "value": value, "hint": hint}


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
        "expired": ("danger", "Expirado"),
        "expiring": ("warning", "A expirar"),
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
