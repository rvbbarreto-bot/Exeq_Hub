"""Pilar 2 + 3 — resolução de CST/cClassTrib/cIndOp na versão normativa publicada."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.fiscal.exceptions import RtcClassificationError
from apps.fiscal.models import RtcClassificationCode, RtcNormativeVersion


def get_published_rtc_version() -> RtcNormativeVersion | None:
    return (
        RtcNormativeVersion.objects.filter(status=RtcNormativeVersion.Status.PUBLISHED)
        .order_by("-published_at", "-id")
        .first()
    )


@transaction.atomic
def publish_rtc_version(version: RtcNormativeVersion) -> RtcNormativeVersion:
    RtcNormativeVersion.objects.filter(
        status=RtcNormativeVersion.Status.PUBLISHED
    ).exclude(pk=version.pk).update(status=RtcNormativeVersion.Status.SUPERSEDED)
    version.status = RtcNormativeVersion.Status.PUBLISHED
    version.published_at = timezone.now()
    version.save(update_fields=["status", "published_at", "updated_at"])
    return version


def resolve_rtc_classification(
    *,
    cst: str = "000",
    c_class_trib: str = "000001",
    c_ind_op: str = "100301",
) -> dict:
    """
    Resolve códigos contra a versão publicada.
    Se não houver versão publicada, retorna unresolved (shadow ainda funciona;
    emit deve ser bloqueado pelo caller se necessário).
    """
    version = get_published_rtc_version()
    if version is None:
        return {
            "status": "unresolved",
            "reason": "no_published_rtc_version",
            "cst": cst,
            "c_class_trib": c_class_trib,
            "c_ind_op": c_ind_op,
            "requires_group": "gIBSCBS",
        }

    def _get(kind: str, code: str) -> RtcClassificationCode:
        row = RtcClassificationCode.objects.filter(
            version=version, kind=kind, code=code, is_active=True
        ).first()
        if row is None:
            raise RtcClassificationError(
                f"Código RTC {kind}={code} ausente na versão {version.version_label}."
            )
        return row

    cst_row = _get(RtcClassificationCode.Kind.CST, cst)
    class_row = _get(RtcClassificationCode.Kind.C_CLASS_TRIB, c_class_trib)
    ind_row = _get(RtcClassificationCode.Kind.C_IND_OP, c_ind_op)

    return {
        "status": "ok",
        "normative_version": version.version_label,
        "nt_refs": version.nt_refs,
        "cst": cst_row.code,
        "cst_description": cst_row.description,
        "c_class_trib": class_row.code,
        "c_class_trib_description": class_row.description,
        "c_ind_op": ind_row.code,
        "c_ind_op_description": ind_row.description,
        "requires_group": cst_row.requires_group or "gIBSCBS",
    }


def seed_minimal_rtc_pack(*, version_label: str = "RTC-2026-TEST-SEED") -> RtcNormativeVersion:
    """Seed mínimo para testes/homologação (Pilar 2+3)."""
    version, created = RtcNormativeVersion.objects.get_or_create(
        version_label=version_label,
        defaults={
            "nt_refs": "LC 214/2025; SE/CGNFS-e NT 009; ADCT art. 125",
            "changelog": "Seed mínimo CST 000 / cClassTrib 000001 / cIndOp 100301 (tributação integral).",
            "owner": "compliance-rtc",
            "status": RtcNormativeVersion.Status.DRAFT,
        },
    )
    codes = [
        (RtcClassificationCode.Kind.CST, "000", "Tributação integral", "gIBSCBS"),
        (
            RtcClassificationCode.Kind.C_CLASS_TRIB,
            "000001",
            "Situação padrão — tributação integral (seed)",
            "gIBSCBS",
        ),
        (
            RtcClassificationCode.Kind.C_IND_OP,
            "100301",
            "Indicador operação seed — serviços em geral (revisar Anexo VII oficial)",
            "",
        ),
    ]
    for kind, code, desc, group in codes:
        RtcClassificationCode.objects.update_or_create(
            version=version,
            kind=kind,
            code=code,
            defaults={
                "description": desc,
                "requires_group": group,
                "is_active": True,
            },
        )
    if version.status != RtcNormativeVersion.Status.PUBLISHED:
        publish_rtc_version(version)
    return version
