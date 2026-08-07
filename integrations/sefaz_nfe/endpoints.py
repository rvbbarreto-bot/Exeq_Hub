"""Endpoints SEFAZ NF-e 4.00 multi-UF (ADR-NFE-001 U4 · G-MULTI-10).

UF pivot continua SP. Catálogo happy path: 10 UFs com URLs homolog/produção.
Fonte de referência comunitária: leiaute wsnfe 4.00 (nfephp/sped-nfe); portais SEFAZ
podem divergir — validar em homolog real antes de prometer produção (G-MULTI-10).
"""

from __future__ import annotations

from dataclasses import dataclass

# Onda U4 — 10 UFs alvo (D-12). Ordem estável para QA matrix.
NFE_MULTI_UF_10: tuple[str, ...] = (
    "SP",  # próprio
    "MG",  # próprio
    "PR",  # próprio
    "RS",  # SEFAZ-RS
    "BA",  # próprio
    "GO",  # próprio
    "PE",  # próprio
    "RJ",  # SVRS
    "SC",  # SVRS
    "ES",  # SVRS
)


@dataclass(frozen=True)
class SefazNfeEndpoints:
    uf: str
    tp_amb: str
    autorizacao: str
    ret_autorizacao: str
    consulta_protocolo: str
    recepcao_evento: str
    status_servico: str
    authority: str = ""  # SP|MG|…|SVRS — para matriz QA


def _ep(
    uf: str,
    tp_amb: str,
    *,
    autorizacao: str,
    ret: str,
    consulta: str,
    evento: str,
    status: str,
    authority: str = "",
) -> SefazNfeEndpoints:
    return SefazNfeEndpoints(
        uf=uf,
        tp_amb=tp_amb,
        autorizacao=autorizacao,
        ret_autorizacao=ret,
        consulta_protocolo=consulta,
        recepcao_evento=evento,
        status_servico=status,
        authority=authority or uf,
    )


def _svrs(uf: str, tp_amb: str) -> SefazNfeEndpoints:
    if tp_amb == "1":
        base = "https://nfe.svrs.rs.gov.br/ws"
    else:
        base = "https://nfe-homologacao.svrs.rs.gov.br/ws"
    return _ep(
        uf,
        tp_amb,
        autorizacao=f"{base}/NfeAutorizacao/NFeAutorizacao4.asmx",
        ret=f"{base}/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        consulta=f"{base}/NfeConsulta/NfeConsulta4.asmx",
        evento=f"{base}/recepcaoevento/recepcaoevento4.asmx",
        status=f"{base}/NfeStatusServico/NfeStatusServico4.asmx",
        authority="SVRS",
    )


def _build_catalog() -> dict[tuple[str, str], SefazNfeEndpoints]:
    cat: dict[tuple[str, str], SefazNfeEndpoints] = {}

    # SP
    cat[("SP", "2")] = _ep(
        "SP",
        "2",
        autorizacao="https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        ret="https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
        consulta="https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
        evento="https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
        status="https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
    )
    cat[("SP", "1")] = _ep(
        "SP",
        "1",
        autorizacao="https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        ret="https://nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
        consulta="https://nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
        evento="https://nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
        status="https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
    )

    # MG
    cat[("MG", "2")] = _ep(
        "MG",
        "2",
        autorizacao="https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
        ret="https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4",
        consulta="https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4",
        evento="https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4",
        status="https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4",
    )
    cat[("MG", "1")] = _ep(
        "MG",
        "1",
        autorizacao="https://nfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
        ret="https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4",
        consulta="https://nfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4",
        evento="https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4",
        status="https://nfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4",
    )

    # PR
    cat[("PR", "2")] = _ep(
        "PR",
        "2",
        autorizacao="https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4",
        ret="https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRetAutorizacao4",
        consulta="https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeConsultaProtocolo4",
        evento="https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRecepcaoEvento4",
        status="https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeStatusServico4",
    )
    cat[("PR", "1")] = _ep(
        "PR",
        "1",
        autorizacao="https://nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4",
        ret="https://nfe.sefa.pr.gov.br/nfe/NFeRetAutorizacao4",
        consulta="https://nfe.sefa.pr.gov.br/nfe/NFeConsultaProtocolo4",
        evento="https://nfe.sefa.pr.gov.br/nfe/NFeRecepcaoEvento4",
        status="https://nfe.sefa.pr.gov.br/nfe/NFeStatusServico4",
    )

    # RS (próprio SEFAZ-RS)
    cat[("RS", "2")] = _ep(
        "RS",
        "2",
        autorizacao="https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        ret="https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        consulta="https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        evento="https://nfe-homologacao.sefazrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
        status="https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
    )
    cat[("RS", "1")] = _ep(
        "RS",
        "1",
        autorizacao="https://nfe.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        ret="https://nfe.sefazrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        consulta="https://nfe.sefazrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        evento="https://nfe.sefazrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
        status="https://nfe.sefazrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
    )

    # BA
    cat[("BA", "2")] = _ep(
        "BA",
        "2",
        autorizacao="https://hnfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx",
        ret="https://hnfe.sefaz.ba.gov.br/webservices/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        consulta="https://hnfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx",
        evento="https://hnfe.sefaz.ba.gov.br/webservices/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
        status="https://hnfe.sefaz.ba.gov.br/webservices/NFeStatusServico4/NFeStatusServico4.asmx",
    )
    cat[("BA", "1")] = _ep(
        "BA",
        "1",
        autorizacao="https://nfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx",
        ret="https://nfe.sefaz.ba.gov.br/webservices/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx",
        consulta="https://nfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx",
        evento="https://nfe.sefaz.ba.gov.br/webservices/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
        status="https://nfe.sefaz.ba.gov.br/webservices/NFeStatusServico4/NFeStatusServico4.asmx",
    )

    # GO
    cat[("GO", "2")] = _ep(
        "GO",
        "2",
        autorizacao="https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        ret="https://homolog.sefaz.go.gov.br/nfe/services/NFeRetAutorizacao4",
        consulta="https://homolog.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4",
        evento="https://homolog.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4",
        status="https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
    )
    cat[("GO", "1")] = _ep(
        "GO",
        "1",
        autorizacao="https://nfe.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
        ret="https://nfe.sefaz.go.gov.br/nfe/services/NFeRetAutorizacao4",
        consulta="https://nfe.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4",
        evento="https://nfe.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4",
        status="https://nfe.sefaz.go.gov.br/nfe/services/NFeStatusServico4",
    )

    # PE
    cat[("PE", "2")] = _ep(
        "PE",
        "2",
        autorizacao="https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4",
        ret="https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRetAutorizacao4",
        consulta="https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeConsultaProtocolo4",
        evento="https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRecepcaoEvento4",
        status="https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeStatusServico4",
    )
    cat[("PE", "1")] = _ep(
        "PE",
        "1",
        autorizacao="https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4",
        ret="https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeRetAutorizacao4",
        consulta="https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeConsultaProtocolo4",
        evento="https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeRecepcaoEvento4",
        status="https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeStatusServico4",
    )

    for uf in ("RJ", "SC", "ES"):
        cat[(uf, "2")] = _svrs(uf, "2")
        cat[(uf, "1")] = _svrs(uf, "1")

    return cat


_CATALOG = _build_catalog()


def list_supported_ufs() -> list[str]:
    return list(NFE_MULTI_UF_10)


def is_uf_supported(uf: str) -> bool:
    return (uf or "").upper().strip() in NFE_MULTI_UF_10


def resolve_endpoints(*, uf: str = "SP", tp_amb: str = "2") -> SefazNfeEndpoints:
    code = (uf or "SP").upper().strip()
    amb = str(tp_amb or "2").strip()[:1] or "2"
    if amb not in {"1", "2"}:
        amb = "2"
    ep = _CATALOG.get((code, amb))
    if ep is None:
        supported = ", ".join(NFE_MULTI_UF_10)
        raise ValueError(
            f"UF {code} fora do catálogo U4 (G-MULTI-10). Suportadas: {supported}"
        )
    return ep


def resolve_inutilizacao_url(*, uf: str = "SP", tp_amb: str = "2") -> str:
    """URL NFeInutilizacao4 (derivada do catálogo U4 — pivot SP explícito)."""
    code = (uf or "SP").upper().strip()
    amb = str(tp_amb or "2").strip()[:1] or "2"
    if code == "SP":
        if amb == "1":
            return "https://nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx"
        return "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx"
    ep = resolve_endpoints(uf=code, tp_amb=amb)
    if ep.authority == "SVRS":
        base = (
            "https://nfe.svrs.rs.gov.br/ws"
            if amb == "1"
            else "https://nfe-homologacao.svrs.rs.gov.br/ws"
        )
        return f"{base}/NfeInutilizacao/NFeInutilizacao4.asmx"
    # Heurística: troca Autorizacao → Inutilizacao no path.
    url = ep.autorizacao
    for a, b in (
        ("NFeAutorizacao4", "NFeInutilizacao4"),
        ("nfeautorizacao4", "nfeinutilizacao4"),
        ("NfeAutorizacao", "NfeInutilizacao"),
        ("NFeAutorizacao", "NFeInutilizacao"),
    ):
        if a in url:
            return url.replace(a, b)
    raise ValueError(f"URL inutilização não resolvida para UF {code}")


def qa_matrix_rows() -> list[dict[str, str]]:
    """Matriz QA (sem rede): UF × ambient × authority × URL autorizacao."""
    rows: list[dict[str, str]] = []
    for uf in NFE_MULTI_UF_10:
        for amb in ("2", "1"):
            ep = resolve_endpoints(uf=uf, tp_amb=amb)
            rows.append(
                {
                    "uf": uf,
                    "tp_amb": amb,
                    "authority": ep.authority,
                    "autorizacao": ep.autorizacao,
                }
            )
    return rows
