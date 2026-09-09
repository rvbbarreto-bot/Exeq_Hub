"""ADR-DAS-DELIVERY-001 — entrega de guia DAS/DARF ao contador (e-mail + WhatsApp)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage

from apps.channel.services import MediaDeliveryError, enqueue_media_notification, enqueue_notification
from apps.das.models import GuiaFiscal
from shared.storage import get_storage

logger = logging.getLogger(__name__)


class DasEmailDeliveryError(Exception):
    """Falha de envio — retry outbox; guia permanece DISPONIVEL."""


def das_delivery_settings(tenant) -> dict[str, Any]:
    raw = (getattr(tenant, "settings", None) or {}).get("das_delivery")
    return raw if isinstance(raw, dict) else {}


def _tenant_settings(tenant) -> dict[str, Any]:
    cfg = getattr(tenant, "settings", None) or {}
    return cfg if isinstance(cfg, dict) else {}


def resolve_accountant_email(
    guia: GuiaFiscal,
    *,
    payload: dict[str, Any] | None = None,
    override: str | None = None,
) -> str:
    if override and str(override).strip():
        return str(override).strip()
    pl = payload or {}
    if pl.get("delivery_email"):
        return str(pl["delivery_email"]).strip()
    cfg = das_delivery_settings(guia.tenant)
    fixed = str(cfg.get("accountant_email") or "").strip()
    if fixed:
        return fixed
    if cfg.get("use_nfe_notify_email_for_das") is True:
        return str(_tenant_settings(guia.tenant).get("nfe_notify_email") or "").strip()
    return ""


def resolve_accountant_whatsapp(
    guia: GuiaFiscal,
    *,
    payload: dict[str, Any] | None = None,
    override: str | None = None,
) -> str:
    if override and str(override).strip():
        return str(override).strip()
    pl = payload or {}
    if pl.get("delivery_phone"):
        return str(pl["delivery_phone"]).strip()
    cfg = das_delivery_settings(guia.tenant)
    return str(cfg.get("accountant_whatsapp") or "").strip()


def _delivery_flags(guia: GuiaFiscal) -> dict[str, Any]:
    meta = guia.metadata if isinstance(guia.metadata, dict) else {}
    delivery = meta.get("delivery")
    return delivery if isinstance(delivery, dict) else {}


def _persist_delivery_flags(guia: GuiaFiscal, delivery: dict[str, Any]) -> None:
    meta = dict(guia.metadata or {})
    meta["delivery"] = delivery
    guia.metadata = meta
    guia.save(update_fields=["metadata", "updated_at"])


def _mark_channel_sent(
    guia: GuiaFiscal,
    *,
    channel: str,
    recipient: str,
    extra: dict[str, Any] | None = None,
) -> None:
    delivery = dict(_delivery_flags(guia))
    now = datetime.now(timezone.utc).isoformat()
    delivery[f"{channel}_sent"] = True
    delivery[f"{channel}_to"] = recipient[:254]
    delivery[f"{channel}_at"] = now
    if extra:
        delivery.update(extra)
    delivery["last_error"] = ""
    _persist_delivery_flags(guia, delivery)


def _channel_already_sent(guia: GuiaFiscal, channel: str) -> bool:
    return bool(_delivery_flags(guia).get(f"{channel}_sent"))


def format_guia_summary(guia: GuiaFiscal, *, compact: bool = False) -> str:
    provider = guia.provider
    cnpj = provider.document if provider else "—"
    legal_name = provider.legal_name if provider else "—"
    tipo = guia.tipo_guia
    lines = [
        f"Tipo: {tipo}",
        f"Competência: {guia.competencia}",
        f"Versão: {guia.versao_atual}",
        f"Prestador: {legal_name}",
        f"CNPJ: {cnpj}",
        f"Principal: R$ {guia.valor_principal}",
        f"Multa: R$ {guia.valor_multa}",
        f"Juros: R$ {guia.valor_juros}",
        f"Total: R$ {guia.valor_total}",
    ]
    if guia.data_vencimento:
        lines.append(f"Vencimento: {guia.data_vencimento.isoformat()}")
    cfg = das_delivery_settings(guia.tenant)
    if cfg.get("include_linha_digitavel_in_message", True) and guia.linha_digitavel:
        lines.append(f"Linha digitável: {guia.linha_digitavel}")
    if cfg.get("include_pix_in_message", True) and guia.pix_copia_cola:
        pix = guia.pix_copia_cola
        if compact and len(pix) > 120:
            pix = pix[:117] + "..."
        lines.append(f"PIX: {pix}")
    if not compact:
        lines.append(f"ID guia: {guia.id}")
    return "\n".join(lines)


def format_ops_guia_message(guia: GuiaFiscal, *, sent_to_accountant: bool) -> str:
    provider = guia.provider
    cnpj = provider.document if provider else "—"
    suffix = "Enviado ao contador." if sent_to_accountant else "Guia disponível."
    return (
        f"{guia.tipo_guia} {guia.competencia} · CNPJ {cnpj} · "
        f"Total R$ {guia.valor_total} · {suffix}"
    )


def _read_pdf_bytes(guia: GuiaFiscal) -> bytes | None:
    if not guia.pdf_file_id:
        return None
    try:
        return get_storage().get(key=guia.pdf_file.object_key)
    except Exception:
        logger.exception("das_delivery_pdf_read_failed guia=%s", guia.id)
        return None


def _pdf_filename(guia: GuiaFiscal) -> str:
    cnpj = (guia.provider.document if guia.provider else "cnpj").replace("/", "")
    safe_cnpj = "".join(ch if ch.isalnum() else "_" for ch in cnpj)[:18]
    return f"guia-{guia.tipo_guia}-{guia.competencia}-{safe_cnpj}.pdf"


def deliver_guia_email(
    *,
    guia: GuiaFiscal,
    payload: dict[str, Any] | None = None,
    override: str | None = None,
    force: bool = False,
) -> bool:
    if guia.status != GuiaFiscal.Status.DISPONIVEL:
        return False
    cfg = das_delivery_settings(guia.tenant)
    if cfg.get("enabled", True) is False:
        return False
    if cfg.get("email_auto", True) is False:
        return False

    recipient = resolve_accountant_email(guia, payload=payload, override=override)
    if not recipient or "@" not in recipient:
        logger.info("das_delivery_no_email_recipient guia=%s", guia.id)
        return False
    if not force and _channel_already_sent(guia, "email"):
        return False

    provider = guia.provider
    subject = (
        f"{guia.tipo_guia} {guia.competencia} · CNPJ {provider.document if provider else '—'}"
        f" · {provider.legal_name if provider else 'Prestador'}"
    )
    body = "Segue guia fiscal capturada.\n\n" + format_guia_summary(guia)
    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(settings, "SERVER_EMAIL", None)
        or "noreply@exeq.local"
    )
    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[recipient],
    )
    pdf_bytes = _read_pdf_bytes(guia)
    if pdf_bytes:
        msg.attach(_pdf_filename(guia), pdf_bytes, "application/pdf")
    else:
        logger.warning("das_delivery_no_pdf guia=%s channel=email", guia.id)

    try:
        sent = msg.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001
        delivery = dict(_delivery_flags(guia))
        delivery["last_error"] = str(exc)[:500]
        _persist_delivery_flags(guia, delivery)
        raise DasEmailDeliveryError(str(exc) or "falha envio e-mail") from exc
    if not sent:
        raise DasEmailDeliveryError("backend e-mail retornou 0 enviados")
    _mark_channel_sent(guia, channel="email", recipient=recipient)
    return True


def deliver_guia_whatsapp(
    *,
    guia: GuiaFiscal,
    payload: dict[str, Any] | None = None,
    override: str | None = None,
    force: bool = False,
) -> bool:
    if guia.status != GuiaFiscal.Status.DISPONIVEL:
        return False
    cfg = das_delivery_settings(guia.tenant)
    if cfg.get("enabled", True) is False:
        return False
    if cfg.get("whatsapp_auto", True) is False:
        return False

    phone = resolve_accountant_whatsapp(guia, payload=payload, override=override)
    if not phone:
        return False
    if not force and _channel_already_sent(guia, "whatsapp"):
        return False

    delivery = dict(_delivery_flags(guia))
    if force or not delivery.get("whatsapp_text_sent"):
        enqueue_notification(
            tenant=guia.tenant,
            phone_e164=phone,
            event_type="guia_fiscal.available",
            message_body=format_guia_summary(guia, compact=True),
        )
        delivery["whatsapp_text_sent"] = True
        _persist_delivery_flags(guia, delivery)

    pdf_bytes = _read_pdf_bytes(guia)
    if pdf_bytes:
        enqueue_media_notification(
            tenant=guia.tenant,
            phone_e164=phone,
            event_type="guia_fiscal.available.pdf",
            filename=_pdf_filename(guia),
            mime_type="application/pdf",
            data=pdf_bytes,
            caption=f"Guia {guia.tipo_guia} · {guia.competencia}",
        )
    else:
        logger.warning("das_delivery_no_pdf guia=%s channel=whatsapp", guia.id)

    _mark_channel_sent(guia, channel="whatsapp", recipient=phone)
    return True


def deliver_guia_to_accountant(
    *,
    guia: GuiaFiscal,
    payload: dict[str, Any] | None = None,
    force: bool = False,
    channels: list[str] | None = None,
) -> bool:
    """Entrega ao contador. Propaga falha de canal (retry outbox)."""
    selected = channels or ["email", "whatsapp"]
    attempted = False
    if "email" in selected:
        attempted = deliver_guia_email(guia=guia, payload=payload, force=force) or attempted
    if "whatsapp" in selected:
        attempted = (
            deliver_guia_whatsapp(guia=guia, payload=payload, force=force) or attempted
        )
    if force:
        delivery = dict(_delivery_flags(guia))
        delivery["last_resent_at"] = datetime.now(timezone.utc).isoformat()
        _persist_delivery_flags(guia, delivery)
    return attempted


def notify_ops_guia_available(
    *,
    tenant,
    guia: GuiaFiscal,
    sent_to_accountant: bool,
    force: bool = False,
) -> None:
    phone = str((_tenant_settings(tenant).get("notify_phone") or "")).strip()
    if not phone:
        return
    if not force and _delivery_flags(guia).get("ops_sent"):
        return
    enqueue_notification(
        tenant=tenant,
        phone_e164=phone,
        event_type="guia_fiscal.ops",
        message_body=format_ops_guia_message(guia, sent_to_accountant=sent_to_accountant),
    )
    delivery = dict(_delivery_flags(guia))
    delivery["ops_sent"] = True
    delivery["ops_to"] = phone[:254]
    _persist_delivery_flags(guia, delivery)


def handle_guia_delivery_outbox(
    *,
    tenant,
    guia_id,
    payload: dict[str, Any] | None = None,
) -> None:
    guia = (
        GuiaFiscal.objects.filter(tenant=tenant, id=guia_id)
        .select_related("provider", "pdf_file")
        .first()
    )
    if guia is None:
        return
    pl = dict(payload or {})
    force = bool(pl.pop("force", False))
    channels = pl.get("channels") or ["email", "whatsapp"]
    has_recipient = bool(
        resolve_accountant_email(guia, payload=pl)
        or resolve_accountant_whatsapp(guia, payload=pl)
    )
    notify_ops_guia_available(
        tenant=tenant,
        guia=guia,
        sent_to_accountant=has_recipient,
        force=force,
    )
    deliver_guia_to_accountant(
        guia=guia,
        payload=pl,
        force=force,
        channels=channels,
    )


def enqueue_guia_redelivery(
    *,
    tenant,
    guia: GuiaFiscal,
    payload: dict[str, Any] | None = None,
) -> None:
    from apps.ops.services import enqueue_outbox

    body = dict(payload or {})
    body.setdefault("force", True)
    body.setdefault("channels", ["email", "whatsapp"])
    enqueue_outbox(
        tenant=tenant,
        event_type="guia_fiscal.redelivery_requested",
        aggregate_type="guia_fiscal",
        aggregate_id=guia.id,
        payload=body,
    )
