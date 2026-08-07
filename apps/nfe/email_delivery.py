"""RF-71 — e-mail XML + DANFE após nfe.authorized (outbox).

Falha de e-mail não altera status fiscal; propaga para retry do outbox.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage

from apps.nfe.artifacts import (
    ensure_authorized_artifacts,
    get_artifact,
    has_danfe_pdf,
    has_xml_authorized,
    read_artifact_bytes,
)
from apps.nfe.models import NfeArtifact, NfeInvoice

logger = logging.getLogger(__name__)


class NfeEmailDeliveryError(Exception):
    """Falha de envio — retry outbox (authorize permanece)."""


def resolve_nfe_email_recipient(
    invoice: NfeInvoice,
    *,
    payload: dict[str, Any] | None = None,
    override: str | None = None,
) -> str:
    """Prioridade: override → payload.email → nfe_notify_email → customer (se auto)."""
    if override and str(override).strip():
        return str(override).strip()
    pl = payload or {}
    if pl.get("email"):
        return str(pl["email"]).strip()
    tenant_settings = invoice.tenant.settings if invoice.tenant_id else {}
    if not isinstance(tenant_settings, dict):
        tenant_settings = {}
    fixed = str(tenant_settings.get("nfe_notify_email") or "").strip()
    if fixed:
        return fixed
    auto = tenant_settings.get("nfe_email_auto")
    if auto is False or str(auto).lower() in {"0", "false", "no"}:
        return ""
    customer = invoice.customer
    if customer is not None:
        return str(getattr(customer, "email", "") or "").strip()
    return ""


def _email_already_sent(invoice: NfeInvoice) -> bool:
    flags = invoice.last_validation if isinstance(invoice.last_validation, dict) else {}
    return bool(flags.get("email_sent"))


def _mark_email_sent(invoice: NfeInvoice, *, to_email: str) -> None:
    flags = dict(invoice.last_validation or {})
    flags["email_sent"] = True
    flags["email_to"] = to_email[:254]
    invoice.last_validation = flags
    invoice.save(update_fields=["last_validation", "updated_at"])


def deliver_authorized_email(
    *,
    invoice: NfeInvoice,
    to_email: str | None = None,
    payload: dict[str, Any] | None = None,
    force: bool = False,
) -> bool:
    """
    Envia XML + DANFE por e-mail.

    Returns True se enviou, False se noop (sem destinatário / já enviado).
    Raises NfeEmailDeliveryError em falha SMTP/backend.
    """
    if invoice.status != NfeInvoice.Status.AUTHORIZED:
        return False
    recipient = resolve_nfe_email_recipient(invoice, payload=payload, override=to_email)
    if not recipient or "@" not in recipient:
        return False
    if not force and _email_already_sent(invoice):
        return False

    ensure_authorized_artifacts(invoice)
    xml_art = get_artifact(invoice, NfeArtifact.Kind.XML_AUTHORIZED)
    pdf_art = get_artifact(invoice, NfeArtifact.Kind.DANFE_PDF)

    series = invoice.series
    number = invoice.number
    ref = f"{series}/{number}" if number is not None else (invoice.access_key or str(invoice.id)[:8])
    key = (invoice.access_key or str(invoice.id))[:44]
    subject = f"NF-e {ref} autorizada"
    body = (
        f"Segue NF-e autorizada {ref}.\n"
        f"Chave de acesso: {invoice.access_key or '—'}\n"
        f"Protocolo: {invoice.protocol or '—'}\n\n"
        "Anexos: XML e DANFE (quando disponíveis).\n"
    )
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
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)[:48]
    if xml_art is not None and has_xml_authorized(invoice):
        try:
            msg.attach(
                f"NFe_{safe}.xml",
                read_artifact_bytes(xml_art),
                "application/xml",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_email_xml_attach_failed invoice=%s", invoice.id)
            raise NfeEmailDeliveryError(f"falha ao anexar XML: {exc}") from exc
    if pdf_art is not None and has_danfe_pdf(invoice):
        try:
            msg.attach(
                f"DANFE_{safe}.pdf",
                read_artifact_bytes(pdf_art),
                "application/pdf",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("nfe_email_pdf_attach_failed invoice=%s", invoice.id)
            raise NfeEmailDeliveryError(f"falha ao anexar DANFE: {exc}") from exc

    if not msg.attachments:
        logger.warning("nfe_email_no_attachments invoice=%s", invoice.id)
        # ainda marca como enviado para não loopar outbox
        _mark_email_sent(invoice, to_email=recipient)
        return True

    try:
        sent = msg.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001
        logger.exception("nfe_email_send_failed invoice=%s to=%s", invoice.id, recipient)
        raise NfeEmailDeliveryError(str(exc) or "falha envio e-mail") from exc
    if not sent:
        raise NfeEmailDeliveryError("backend e-mail retornou 0 enviados")
    _mark_email_sent(invoice, to_email=recipient)
    return True
