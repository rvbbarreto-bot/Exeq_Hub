"""Manifestação do destinatário — NF-e de entrada."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.certificates import load_primary_pfx_material
from apps.nfe.entrada.artifacts import store_manifest_xml
from apps.nfe.entrada.exceptions import ManifestationError
from apps.nfe.entrada.feature import require_nfe_entrada_enabled
from apps.nfe.entrada.models import NfeEntradaDocument, NfeEntradaManifestation
from apps.nfe.entrada.services.distribuicao import schedule_distribuicao_sync
from integrations.sefaz_nfe.evento_cancel import NfeEventoBuildError
from integrations.sefaz_nfe.manifestacao.evento import (
    TP_EVENTO_CIENCIA,
    TP_EVENTO_CONFIRMACAO,
    TP_EVENTO_DESCONHECIMENTO,
    TP_EVENTO_NAO_REALIZADA,
    build_manifest_env_evento_xml,
)
from integrations.sefaz_nfe.manifestacao.transmit import is_manifest_accepted, transmit_manifestacao_evento
from integrations.sefaz_nfe.sign import sign_evento_nfe_xml

logger = logging.getLogger(__name__)

_CONFIRMATION_REQUIRED = frozenset(
    {
        TP_EVENTO_CONFIRMACAO,
        TP_EVENTO_DESCONHECIMENTO,
        TP_EVENTO_NAO_REALIZADA,
    }
)

_MANIFEST_STATUS = {
    TP_EVENTO_CIENCIA: NfeEntradaDocument.ManifestStatus.CIENCIA,
    TP_EVENTO_CONFIRMACAO: NfeEntradaDocument.ManifestStatus.CONFIRMADA,
    TP_EVENTO_DESCONHECIMENTO: NfeEntradaDocument.ManifestStatus.DESCONHECIDA,
    TP_EVENTO_NAO_REALIZADA: NfeEntradaDocument.ManifestStatus.NAO_REALIZADA,
}


@dataclass(frozen=True)
class ManifestResult:
    success: bool
    manifestation: NfeEntradaManifestation
    c_stat: str
    protocol: str
    idempotent: bool = False


def _next_n_seq(*, document: NfeEntradaDocument, tp_evento: str) -> int:
    last = (
        NfeEntradaManifestation.objects.filter(
            tenant_id=document.tenant_id,
            document_id=document.id,
            tp_evento=tp_evento,
        )
        .order_by("-n_seq")
        .first()
    )
    if last is None:
        return 1
    return int(last.n_seq or 1) + 1


def _existing_accepted(
    *, document: NfeEntradaDocument, tp_evento: str
) -> NfeEntradaManifestation | None:
    return NfeEntradaManifestation.objects.filter(
        tenant_id=document.tenant_id,
        document_id=document.id,
        tp_evento=tp_evento,
        status=NfeEntradaManifestation.Status.ACCEPTED,
    ).first()


def manifest_entrada_document(
    *,
    document: NfeEntradaDocument,
    tp_evento: str,
    actor_user: User | None = None,
    actor_ip: str | None = None,
    justificativa: str | None = None,
    confirmed: bool = False,
) -> ManifestResult:
    """
    Envia manifestação do destinatário.

    Confirmação (210200), desconhecimento (210220) e op. não realizada (210240)
    exigem ``confirmed=True`` (ação explícita do operador).
    """
    require_nfe_entrada_enabled(tenant=document.tenant)
    te = str(tp_evento or "").strip()
    if te not in {
        TP_EVENTO_CIENCIA,
        TP_EVENTO_CONFIRMACAO,
        TP_EVENTO_DESCONHECIMENTO,
        TP_EVENTO_NAO_REALIZADA,
    }:
        raise ManifestationError(f"tpEvento inválido: {tp_evento}")

    if te in _CONFIRMATION_REQUIRED and not confirmed:
        raise ManifestationError(
            "Confirmação explícita obrigatória para este evento de manifestação."
        )

    access_key = "".join(c for c in document.access_key if c.isdigit())[:44]
    if len(access_key) != 44:
        raise ManifestationError("Documento sem chave de acesso válida.")

    existing = _existing_accepted(document=document, tp_evento=te)
    if existing is not None:
        return ManifestResult(
            success=True,
            manifestation=existing,
            c_stat=existing.c_stat,
            protocol=existing.protocol,
            idempotent=True,
        )

    recipient_cnpj = "".join(
        c for c in (document.recipient_cnpj or document.provider.document) if c.isdigit()
    )[:14]
    if len(recipient_cnpj) != 14:
        raise ManifestationError("CNPJ destinatário inválido.")

    tp_amb = str(
        getattr(document.provider, "tp_amb", None)
        or getattr(settings, "NFE_DEFAULT_TP_AMB", "2")
        or "2"
    )[:1]
    cursor_tp_amb = tp_amb
    try:
        cursor = document.provider.nfe_distribuicao_cursor
        cursor_tp_amb = str(cursor.tp_amb or tp_amb)[:1]
    except Exception:
        pass

    n_seq = _next_n_seq(document=document, tp_evento=te)
    correlation_id = uuid.uuid4()

    try:
        unsigned = build_manifest_env_evento_xml(
            access_key=access_key,
            cnpj=recipient_cnpj,
            tp_evento=te,
            tp_amb=cursor_tp_amb,
            n_seq=n_seq,
            justificativa=justificativa,
        )
        pfx_bytes, password = load_primary_pfx_material(
            tenant=document.tenant,
            cnpj=recipient_cnpj,
            purpose="nfe",
        )
        signed = sign_evento_nfe_xml(
            env_evento_xml=unsigned,
            pfx_bytes=pfx_bytes,
            password=password,
        )
    except NfeEventoBuildError as exc:
        raise ManifestationError(str(exc)) from exc
    except Exception as exc:
        raise ManifestationError(f"Falha ao preparar evento: {exc}") from exc

    transmitted = transmit_manifestacao_evento(
        signed_env_evento_xml=signed,
        access_key=access_key,
        tp_amb=cursor_tp_amb,
        tp_evento=te,
        pfx_bytes=pfx_bytes,
        password=password,
    )

    accepted = is_manifest_accepted(transmitted.c_stat)
    status = (
        NfeEntradaManifestation.Status.ACCEPTED
        if accepted
        else NfeEntradaManifestation.Status.REJECTED
    )

    with transaction.atomic():
        stored = store_manifest_xml(
            tenant_id=document.tenant_id,
            document_id=document.id,
            tp_evento=te,
            xml_bytes=signed,
        )
        manifestation = NfeEntradaManifestation.objects.create(
            tenant_id=document.tenant_id,
            document=document,
            tp_evento=te,
            n_seq=n_seq,
            protocol=transmitted.protocol,
            c_stat=transmitted.c_stat,
            x_motivo=transmitted.x_motivo,
            status=status,
            actor_user=actor_user,
            actor_ip=actor_ip,
            stored_file=stored,
            correlation_id=correlation_id,
        )

        if accepted:
            document.manifest_status = _MANIFEST_STATUS.get(
                te, NfeEntradaDocument.ManifestStatus.NONE
            )
            document.save(update_fields=["manifest_status", "updated_at"])

    if accepted and te == TP_EVENTO_CIENCIA:
        try:
            schedule_distribuicao_sync(tenant=document.tenant, provider=document.provider)
        except Exception:
            logger.exception(
                "nfe_entrada post_ciencia sync enqueue failed doc=%s",
                document.id,
            )

    if not accepted:
        raise ManifestationError(
            f"Manifestação rejeitada: {transmitted.c_stat} — {transmitted.x_motivo}"
        )

    return ManifestResult(
        success=True,
        manifestation=manifestation,
        c_stat=transmitted.c_stat,
        protocol=transmitted.protocol,
    )
