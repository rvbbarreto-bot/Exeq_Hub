"""Orquestra RTC na emissão NFS-e (pilares 1/2/4/5)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings

from apps.fiscal.exceptions import NationalCatalogError, RtcClassificationError
from apps.fiscal.rtc_assessment import compute_ibscbs_base
from apps.fiscal.rtc_catalog_guard import assert_national_service_code
from apps.fiscal.rtc_classification import resolve_rtc_classification
from apps.fiscal.rtc_forensic import build_forensic_snapshot, merge_snapshot


def rtc_mode() -> str:
    mode = (getattr(settings, "RTC_NFSEN_MODE", "shadow") or "shadow").strip().lower()
    if mode not in {"off", "shadow", "emit"}:
        return "shadow"
    return mode


def build_rtc_emission_context(
    *,
    service,
    rule,
    amount_cents: int,
    competence_date: date,
    iss_payload: dict,
    layout: str = "nfsen",
) -> dict:
    """
    Retorna:
      resolved_params_extra (rtc + national_catalog),
      snapshot (iss + forensic),
      errors handled by caller
    """
    mode = rtc_mode()
    national = assert_national_service_code(service=service)

    if mode == "off":
        forensic = build_forensic_snapshot(
            iss_payload=iss_payload,
            rtc_block={"status": "off"},
            national_catalog=national,
            layout=layout,
        )
        return {
            "mode": mode,
            "params": merge_snapshot(iss_payload, forensic),
            "focus_rtc_fields": {},
        }

    classification = resolve_rtc_classification()
    assessed = compute_ibscbs_base(
        amount_cents=amount_cents,
        iss_rate=Decimal(str(rule.iss_rate)),
        pis_rate=Decimal(str(rule.pis_rate)),
        cofins_rate=Decimal(str(rule.cofins_rate)),
        competence_date=competence_date,
    )
    rtc_block = {
        "status": "computed",
        "mode": mode,
        "fin_nfse": 0,
        "ind_final": 0,
        "classification": classification,
        "assessment": assessed,
    }
    focus_fields = focus_rtc_field_map(rtc_block) if mode == "emit" else {}
    rtc_block["focus_fields"] = focus_fields

    forensic = build_forensic_snapshot(
        iss_payload=iss_payload,
        rtc_block=rtc_block,
        national_catalog=national,
        layout=layout,
    )
    return {
        "mode": mode,
        "params": merge_snapshot(iss_payload, forensic),
        "focus_rtc_fields": focus_fields,
    }


def focus_rtc_field_map(rtc_block: dict) -> dict:
    """
    Mapa snake_case Focus / DPS Nacional (contrato evolutivo).
    Em modo emit, mesclado no payload nfsen.
    Nomes alinhados ao estilo Focus; ajustar quando doc Focus listar campos oficiais.
    """
    cls = rtc_block.get("classification") or {}
    asm = rtc_block.get("assessment") or {}
    return {
        "finalidade_nfsen": int(rtc_block.get("fin_nfse") or 0),
        "indicador_destinatario_consumidor_final": int(rtc_block.get("ind_final") or 0),
        "codigo_indicador_operacao": cls.get("c_ind_op") or "",
        "situacao_tributaria_ibscbs": cls.get("cst") or "",
        "classificacao_tributaria_ibscbs": cls.get("c_class_trib") or "",
        "base_calculo_ibscbs": float(asm.get("v_bc") or 0),
        "percentual_aliquota_cbs": float(Decimal(asm.get("p_cbs") or 0) * 100),
        "percentual_aliquota_ibs": float(Decimal(asm.get("p_ibs") or 0) * 100),
        "percentual_aliquota_ibs_uf": float(Decimal(asm.get("p_ibs_uf") or 0) * 100),
        "percentual_aliquota_ibs_municipio": float(
            Decimal(asm.get("p_ibs_mun") or 0) * 100
        ),
        "valor_cbs": float(asm.get("v_cbs") or 0),
        "valor_ibs": float(asm.get("v_ibs") or 0),
        "valor_ibs_uf": float(asm.get("v_ibs_uf") or 0),
        "valor_ibs_municipio": float(asm.get("v_ibs_mun") or 0),
    }


# re-export errors for callers
__all__ = [
    "build_rtc_emission_context",
    "focus_rtc_field_map",
    "rtc_mode",
    "NationalCatalogError",
    "RtcClassificationError",
]
