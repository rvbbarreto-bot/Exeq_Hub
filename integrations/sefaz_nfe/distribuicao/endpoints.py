"""Endpoints NFeDistribuicaoDFe — Ambiente Nacional (NT 2014.002)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NfeDistribuicaoEndpoints:
    distribuicao: str
    authority: str = "AN"


_HOMOLOG = NfeDistribuicaoEndpoints(
    distribuicao="https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    authority="AN-HOM",
)

_PRODUCTION = NfeDistribuicaoEndpoints(
    distribuicao="https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    authority="AN-PROD",
)


def resolve_distribuicao_endpoints(*, tp_amb: str) -> NfeDistribuicaoEndpoints:
    amb = str(tp_amb or "2").strip()[:1]
    if amb == "1":
        return _PRODUCTION
    return _HOMOLOG
