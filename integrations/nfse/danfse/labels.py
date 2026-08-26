"""Rótulos de exibição DANFSe — códigos XML → texto NT/gov (somente PDF)."""

from __future__ import annotations


def label_situacao(cstat: str, *, cancelled: bool = False) -> str:
    if cancelled or cstat.upper() in {"CANCELADA", "101"}:
        return "Cancelada"
    mapping = {
        "100": "NFS-e Gerada",
        "102": "Substituída",
    }
    return mapping.get(cstat.strip(), cstat or "—")


def label_finalidade(code: str) -> str:
    mapping = {
        "1": "Substituição",
        "2": "Ajuste",
    }
    raw = (code or "").strip()
    if raw in {"", "0"}:
        return "-"
    return mapping.get(raw, raw or "-")


def label_emitente(code: str) -> str:
    mapping = {
        "1": "Prestador",
        "2": "Tomador",
        "3": "Intermediário",
    }
    raw = (code or "").strip()
    return mapping.get(raw, raw or "Prestador")


def label_op_simp_nac(code: str) -> str:
    mapping = {
        "1": "Não Optante",
        "2": "Optante — MEI",
        "3": "Optante — ME/EPP",
    }
    return mapping.get((code or "").strip(), code or "—")


def label_reg_ap_trib_sn(code: str) -> str:
    mapping = {
        "1": "Regime de apuração dos tributos federais e municipal pelo SN",
        "2": "Regime de apuração dos tributos federais pelo SN e ISSQN por fora",
        "3": "Regime de apuração dos tributos federais e municipal por fora",
    }
    return mapping.get((code or "").strip(), code or "—")


def label_reg_esp_trib(code: str) -> str:
    mapping = {
        "0": "Nenhum",
        "1": "Microempresa Municipal",
        "2": "Estimativa",
        "3": "Sociedade de Profissionais",
        "4": "Cooperativa",
        "5": "Microempresário Individual (MEI)",
        "6": "Microempresa ou Empresa de Pequeno Porte (ME/EPP)",
    }
    return mapping.get((code or "").strip(), code or "—")


def label_trib_issqn(code: str) -> str:
    mapping = {
        "1": "Operação Tributável",
        "2": "Imunidade",
        "3": "Exportação de serviço",
        "4": "Não Incidência",
    }
    return mapping.get((code or "").strip(), code or "—")


def label_tp_ret_issqn(code: str) -> str:
    mapping = {
        "1": "Não Retido",
        "2": "Retido pelo Tomador",
        "3": "Retido pelo Intermediário",
    }
    return mapping.get((code or "").strip(), code or "—")


def label_amb_gerador(code: str) -> str:
    mapping = {
        "1": "Prefeitura",
        "2": "Sistema Nacional NFS-e",
    }
    return mapping.get((code or "").strip(), code or "—")
