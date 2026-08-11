"""Resumo de integração SEFIN/ADN a partir da NfIssue (sem I/O de rede)."""

from __future__ import annotations

import re
from typing import Any

from apps.issuance.models import NfIssue

# Portal oficial NFS-e Nacional
CONSULTA_PUBLICA_URL = "https://www.nfse.gov.br/consultapublica"
PORTAL_CONTRIBUINTE_URL = "https://www.nfse.gov.br/EmissorNacional"


def _text(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<]*)</{tag}>", xml or "", flags=re.I)
    return (m.group(1).strip() if m else "") or ""


def sefin_integration_summary(issue: NfIssue) -> dict[str, Any]:
    """
    Interpreta se a emissão entrou no Ambiente Nacional (SEFIN).

    Fonte de verdade: focus_status_raw (resposta SEFIN) + XML + status local.
    """
    raw = issue.focus_status_raw if isinstance(issue.focus_status_raw, dict) else {}
    xml = str(raw.get("xml") or "")
    chave = (
        (issue.focus_ref or "").strip()
        or str(raw.get("chaveAcesso") or raw.get("chave_acesso") or "").strip()
    )
    n_nfse = _text(xml, "nNFSe") or str(raw.get("nNFSe") or "").strip()
    c_stat = _text(xml, "cStat") or str(raw.get("cStat") or "").strip()
    amb_ger = _text(xml, "ambGer")
    tp_amb = _text(xml, "tpAmb") or str(
        (issue.internal_payload or {}).get("tp_amb")
        if isinstance(issue.internal_payload, dict)
        else ""
    )
    tipo_ambiente = str(raw.get("tipoAmbiente") or "").strip()
    ver_aplic = _text(xml, "verAplic") or str(raw.get("versaoAplicativo") or "")
    http_status = raw.get("http_status")
    provider = str(raw.get("provider") or "").strip()
    mode = str(raw.get("mode") or "").strip()

    sefin_ok = (
        issue.status == NfIssue.Status.AUTHORIZED
        and bool(chave)
        and (provider == "sefin" or bool(xml and "sped.fazenda.gov.br" in xml))
        and (c_stat in {"", "100"} or int(str(c_stat) or "0") == 100)
    )
    # Resposta SEFIN real (não stub local)
    http_ok = http_status in (200, 201) or (
        mode == "http" and issue.status == NfIssue.Status.AUTHORIZED and bool(chave)
    )
    integrated = bool(sefin_ok and (http_ok or (mode == "http" and chave)))

    ambiente_label = "produção"
    if str(tipo_ambiente) == "2" or str(tp_amb) == "2":
        ambiente_label = "homologação / produção restrita"
    elif str(tipo_ambiente) == "1" or str(tp_amb) == "1":
        ambiente_label = "produção"

    return {
        "integrated": integrated,
        "provider": provider or ("sefin" if integrated else ""),
        "mode": mode,
        "chave_acesso": chave,
        "n_nfse": n_nfse,
        "c_stat": c_stat or ("100" if integrated else ""),
        "amb_ger": amb_ger,
        "tp_amb": str(tp_amb or tipo_ambiente or ""),
        "tipo_ambiente": tipo_ambiente,
        "ambiente_label": ambiente_label,
        "ver_aplic": ver_aplic,
        "http_status": http_status,
        "consulta_publica_url": CONSULTA_PUBLICA_URL,
        "portal_contribuinte_url": PORTAL_CONTRIBUINTE_URL,
        "reject_local": issue.status == NfIssue.Status.REJECTED
        and not raw
        and bool(issue.rejection_code),
        "rejection_code": issue.rejection_code or "",
    }
