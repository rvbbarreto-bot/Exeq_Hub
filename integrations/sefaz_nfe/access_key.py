"""Chave de acesso NF-e (44 dígitos) — calculo estrutural + DV módulo 11."""

from __future__ import annotations


UF_IBGE_CODE = {
    "AC": "12",
    "AL": "27",
    "AM": "13",
    "AP": "16",
    "BA": "29",
    "CE": "23",
    "DF": "53",
    "ES": "32",
    "GO": "52",
    "MA": "21",
    "MG": "31",
    "MS": "50",
    "MT": "51",
    "PA": "15",
    "PB": "25",
    "PE": "26",
    "PI": "22",
    "PR": "41",
    "RJ": "33",
    "RN": "24",
    "RO": "11",
    "RR": "14",
    "RS": "43",
    "SC": "42",
    "SE": "28",
    "SP": "35",
    "TO": "17",
}


def check_digit_mod11(body43: str) -> str:
    if len(body43) != 43 or not body43.isdigit():
        raise ValueError("base da chave deve ter 43 dígitos")
    weights = [2, 3, 4, 5, 6, 7, 8, 9]
    total = 0
    wi = 0
    for digit in reversed(body43):
        total += int(digit) * weights[wi]
        wi = (wi + 1) % len(weights)
    rem = total % 11
    dv = 0 if rem in (0, 1) else 11 - rem
    return str(dv)


def build_access_key(
    *,
    uf: str,
    issue_date_iso: str,
    cnpj: str,
    series: int,
    number: int,
    model: str = "55",
    tp_emis: str = "1",
    cnf: int | None = None,
) -> str:
    """Monta chave 44 dígitos (cUF AAMM CNPJ mod serie nNF tpEmis cNF DV)."""
    uf_code = UF_IBGE_CODE.get((uf or "").upper().strip(), "35")
    yymm = (issue_date_iso or "")[:7].replace("-", "")[2:6]
    if len(yymm) != 4:
        yymm = "0000"
    cnpj_d = "".join(ch for ch in str(cnpj) if ch.isdigit()).zfill(14)[:14]
    serie = str(int(series)).zfill(3)[:3]
    nnf = str(int(number)).zfill(9)[:9]
    if cnf is None:
        cnf = (int(number) * 7919 + int(series) * 97) % 100_000_000
    cnf_s = str(int(cnf) % 100_000_000).zfill(8)
    body = f"{uf_code}{yymm}{cnpj_d}{model}{serie}{nnf}{tp_emis}{cnf_s}"
    return body + check_digit_mod11(body)
