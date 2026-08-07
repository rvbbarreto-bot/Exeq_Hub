from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.channel.models import ChannelNotification, ChannelSession
from integrations.whatsapp.gateway import get_whatsapp_gateway

DEBOUNCE_SECONDS = 5


class MediaDeliveryError(Exception):
    """Falha no envio de mídia — propaga para retry do outbox (WA-ART-03/04)."""


@transaction.atomic
def ingest_inbound_message(
    *,
    tenant,
    phone_e164: str,
    message_id: str,
    text: str,
) -> ChannelSession:
    """Debounce: mesma mensagem/janela curta atualiza uma sessão, não duplica."""
    idempotency_key = f"{phone_e164}:{message_id}"
    existing = ChannelSession.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        existing.draft_payload = {**(existing.draft_payload or {}), "text": text}
        existing.last_message_at = timezone.now()
        existing.save(update_fields=["draft_payload", "last_message_at", "updated_at"])
        return existing

    window_start = timezone.now() - timedelta(seconds=DEBOUNCE_SECONDS)
    recent = (
        ChannelSession.objects.select_for_update()
        .filter(
            tenant=tenant,
            phone_e164=phone_e164,
            status=ChannelSession.Status.COLLECTING,
            last_message_at__gte=window_start,
        )
        .order_by("-last_message_at")
        .first()
    )
    if recent:
        recent.draft_payload = {
            **(recent.draft_payload or {}),
            "text": text,
            "last_message_id": message_id,
        }
        recent.last_message_at = timezone.now()
        recent.save(update_fields=["draft_payload", "last_message_at", "updated_at"])
        return recent

    return ChannelSession.objects.create(
        tenant=tenant,
        idempotency_key=idempotency_key,
        phone_e164=phone_e164,
        draft_payload={"text": text, "last_message_id": message_id},
        last_message_at=timezone.now(),
    )


def enqueue_notification(
    *,
    tenant,
    phone_e164: str,
    event_type: str,
    message_body: str,
    session: ChannelSession | None = None,
    nf_issue=None,
    nfe_invoice=None,
) -> ChannelNotification:
    notification = ChannelNotification.objects.create(
        tenant=tenant,
        session=session,
        nf_issue=nf_issue,
        nfe_invoice=nfe_invoice,
        phone_e164=phone_e164,
        event_type=event_type,
        message_body=message_body,
    )
    gateway = get_whatsapp_gateway(tenant=tenant)
    result = gateway.send_text(phone_e164=phone_e164, text=message_body)
    notification.provider = result.get("provider", "")
    notification.provider_ref = result.get("ref", "")
    notification.status = (
        ChannelNotification.Status.SENT
        if result.get("ok")
        else ChannelNotification.Status.FAILED
    )
    notification.save(update_fields=["provider", "provider_ref", "status", "updated_at"])
    return notification


def enqueue_media_notification(
    *,
    tenant,
    phone_e164: str,
    event_type: str,
    filename: str,
    mime_type: str,
    data: bytes,
    caption: str = "",
    session: ChannelSession | None = None,
    nf_issue=None,
    nfe_invoice=None,
) -> ChannelNotification:
    """Envia documento pelo WhatsApp e audita em ChannelNotification."""
    notification = ChannelNotification.objects.create(
        tenant=tenant,
        session=session,
        nf_issue=nf_issue,
        nfe_invoice=nfe_invoice,
        phone_e164=phone_e164,
        event_type=event_type,
        message_body=caption or filename,
    )
    gateway = get_whatsapp_gateway(tenant=tenant)
    result = gateway.send_media(
        phone_e164=phone_e164,
        filename=filename,
        mime_type=mime_type,
        data=data,
        caption=caption or filename,
    )
    notification.provider = result.get("provider", "")
    notification.provider_ref = result.get("ref", "")
    notification.status = (
        ChannelNotification.Status.SENT
        if result.get("ok")
        else ChannelNotification.Status.FAILED
    )
    notification.save(update_fields=["provider", "provider_ref", "status", "updated_at"])
    if not result.get("ok"):
        raise MediaDeliveryError(
            result.get("error") or f"Falha ao enviar {filename} via WhatsApp"
        )
    return notification


def _artifact_bytes(artifact) -> bytes:
    from shared.storage import get_storage

    stored = artifact.stored_file
    return get_storage().get(key=stored.object_key)


def _already_sent(*, tenant, nf_issue, phone_e164: str, event_type: str) -> bool:
    return ChannelNotification.objects.filter(
        tenant=tenant,
        nf_issue=nf_issue,
        phone_e164=phone_e164,
        event_type=event_type,
        status=ChannelNotification.Status.SENT,
    ).exists()


def _already_sent_nfe(*, tenant, nfe_invoice, phone_e164: str, event_type: str) -> bool:
    return ChannelNotification.objects.filter(
        tenant=tenant,
        nfe_invoice=nfe_invoice,
        phone_e164=phone_e164,
        event_type=event_type,
        status=ChannelNotification.Status.SENT,
    ).exists()


def deliver_nf_artifacts(
    *,
    tenant,
    nf_issue,
    phone_e164: str,
    session: ChannelSession | None = None,
) -> list[ChannelNotification]:
    """WA-ART — envia texto + PDF + XML ao telefone; falha de mídia propaga retry.

    Idempotente por event_type: retry do outbox não reenvia o que já foi SENT.
    """
    from apps.issuance.artifacts import ensure_authorized_artifacts
    from apps.issuance.models import NfArtifact

    ensure_authorized_artifacts(nf_issue)
    ref = nf_issue.focus_ref or str(nf_issue.id)
    notes: list[ChannelNotification] = []

    if not _already_sent(
        tenant=tenant,
        nf_issue=nf_issue,
        phone_e164=phone_e164,
        event_type="nf_issue.authorized",
    ):
        notes.append(
            enqueue_notification(
                tenant=tenant,
                phone_e164=phone_e164,
                event_type="nf_issue.authorized",
                message_body=f"NFS-e autorizada. Ref: {ref}\nSeguem PDF e XML da nota.",
                session=session,
                nf_issue=nf_issue,
            )
        )

    artifacts = NfArtifact.objects.filter(nf_issue=nf_issue).select_related("stored_file")
    by_kind = {a.kind: a for a in artifacts}
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in ref)[:48]

    pdf = by_kind.get(NfArtifact.Kind.PDF)
    if pdf is not None and not _already_sent(
        tenant=tenant,
        nf_issue=nf_issue,
        phone_e164=phone_e164,
        event_type="nf_issue.authorized.pdf",
    ):
        notes.append(
            enqueue_media_notification(
                tenant=tenant,
                phone_e164=phone_e164,
                event_type="nf_issue.authorized.pdf",
                filename=f"DANFSe_{safe_ref}.pdf",
                mime_type="application/pdf",
                data=_artifact_bytes(pdf),
                caption=f"DANFSe — NFS-e {ref}",
                session=session,
                nf_issue=nf_issue,
            )
        )

    xml = by_kind.get(NfArtifact.Kind.XML)
    if xml is not None and not _already_sent(
        tenant=tenant,
        nf_issue=nf_issue,
        phone_e164=phone_e164,
        event_type="nf_issue.authorized.xml",
    ):
        notes.append(
            enqueue_media_notification(
                tenant=tenant,
                phone_e164=phone_e164,
                event_type="nf_issue.authorized.xml",
                filename=f"NFSe_{safe_ref}.xml",
                mime_type="application/xml",
                data=_artifact_bytes(xml),
                caption=f"XML — NFS-e {ref}",
                session=session,
                nf_issue=nf_issue,
            )
        )

    return notes


def deliver_nfe_artifacts(
    *,
    tenant,
    nfe_invoice,
    phone_e164: str,
    session: ChannelSession | None = None,
) -> list[ChannelNotification]:
    """RF-72 — texto + DANFE PDF + XML ao telefone da sessão/canal.

    Idempotente por event_type; falha de mídia propaga retry do outbox.
    Só deve ser chamado quando o canal liga a nfe.authorized (sessão).
    """
    from apps.nfe.artifacts import ensure_authorized_artifacts
    from apps.nfe.models import NfeArtifact

    ensure_authorized_artifacts(nfe_invoice)
    ref = nfe_invoice.access_key or f"{nfe_invoice.series}-{nfe_invoice.number}"
    notes: list[ChannelNotification] = []

    if not _already_sent_nfe(
        tenant=tenant,
        nfe_invoice=nfe_invoice,
        phone_e164=phone_e164,
        event_type="nfe.authorized",
    ):
        series = nfe_invoice.series
        number = nfe_invoice.number
        ref_num = f"{series}/{number}" if number is not None else ref
        notes.append(
            enqueue_notification(
                tenant=tenant,
                phone_e164=phone_e164,
                event_type="nfe.authorized",
                message_body=(
                    f"NF-e autorizada. {ref_num}\nSeguem DANFE (PDF) e XML da nota."
                ),
                session=session,
                nfe_invoice=nfe_invoice,
            )
        )

    artifacts = NfeArtifact.objects.filter(invoice=nfe_invoice).select_related(
        "stored_file"
    )
    by_kind = {a.kind: a for a in artifacts}
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(ref))[
        :48
    ]

    pdf = by_kind.get(NfeArtifact.Kind.DANFE_PDF)
    if pdf is not None and not _already_sent_nfe(
        tenant=tenant,
        nfe_invoice=nfe_invoice,
        phone_e164=phone_e164,
        event_type="nfe.authorized.pdf",
    ):
        notes.append(
            enqueue_media_notification(
                tenant=tenant,
                phone_e164=phone_e164,
                event_type="nfe.authorized.pdf",
                filename=f"DANFE_{safe_ref}.pdf",
                mime_type="application/pdf",
                data=_artifact_bytes(pdf),
                caption=f"DANFE — NF-e {ref}",
                session=session,
                nfe_invoice=nfe_invoice,
            )
        )

    xml = by_kind.get(NfeArtifact.Kind.XML_AUTHORIZED)
    if xml is not None and not _already_sent_nfe(
        tenant=tenant,
        nfe_invoice=nfe_invoice,
        phone_e164=phone_e164,
        event_type="nfe.authorized.xml",
    ):
        notes.append(
            enqueue_media_notification(
                tenant=tenant,
                phone_e164=phone_e164,
                event_type="nfe.authorized.xml",
                filename=f"NFe_{safe_ref}.xml",
                mime_type="application/xml",
                data=_artifact_bytes(xml),
                caption=f"XML — NF-e {ref}",
                session=session,
                nfe_invoice=nfe_invoice,
            )
        )

    return notes
