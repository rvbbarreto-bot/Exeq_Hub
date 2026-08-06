"""Endpoints SEFAZ NF-e 4.00 por UF (pivot SP)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SefazNfeEndpoints:
    uf: str
    tp_amb: str
    autorizacao: str
    ret_autorizacao: str
    consulta_protocolo: str
    recepcao_evento: str
    status_servico: str


# Fontes: Manual de Orientação do Contribuinte / portal SEFAZ-SP (NFe 4.00).
_SP_HOMOLOG = SefazNfeEndpoints(
    uf="SP",
    tp_amb="2",
    autorizacao="https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
    ret_autorizacao="https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
    consulta_protocolo="https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
    recepcao_evento="https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
    status_servico="https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
)

_SP_PROD = SefazNfeEndpoints(
    uf="SP",
    tp_amb="1",
    autorizacao="https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
    ret_autorizacao="https://nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
    consulta_protocolo="https://nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
    recepcao_evento="https://nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
    status_servico="https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
)


def resolve_endpoints(*, uf: str = "SP", tp_amb: str = "2") -> SefazNfeEndpoints:
    code = (uf or "SP").upper().strip()
    amb = str(tp_amb or "2").strip()
    if code != "SP":
        raise ValueError(f"UF {code} sem catálogo HTTP na onda SP (ADR-NFE-001 U3)")
    return _SP_PROD if amb == "1" else _SP_HOMOLOG
