"""Mapeamento CSOSN → grupo XML ICMS (Simples Nacional)."""

from __future__ import annotations


def map_csosn_to_xml_group(csosn: str) -> str:
    code = (csosn or "").strip().zfill(3)
    return {
        "101": "ICMSSN101",
        "102": "ICMSSN102",
        "103": "ICMSSN102",
        "201": "ICMSSN201",
        "202": "ICMSSN202",
        "203": "ICMSSN202",
        "300": "ICMSSN102",
        "400": "ICMSSN400",
        "500": "ICMSSN500",
        "900": "ICMSSN900",
    }.get(code, "ICMSSN102")
