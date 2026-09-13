"""Endpoints SEFAZ NFC-e mod 65 — pivot SP (homolog + produção)."""

from __future__ import annotations

from dataclasses import dataclass

from integrations.sefaz_nfe.endpoints import SefazNfeEndpoints


@dataclass(frozen=True)
class SefazNfceEndpoints:
    uf: str
    tp_amb: str
    autorizacao: str
    ret_autorizacao: str
    consulta_protocolo: str
    recepcao_evento: str
    status_servico: str
    qr_base_url: str


def _sp(tp_amb: str) -> SefazNfceEndpoints:
    if tp_amb == "1":
        base = "https://nfce.fazenda.sp.gov.br/ws"
        qr = "https://www.nfce.fazenda.sp.gov.br/NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
    else:
        base = "https://homologacao.nfce.fazenda.sp.gov.br/ws"
        qr = (
            "https://www.homologacao.nfce.fazenda.sp.gov.br/"
            "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
        )
    return SefazNfceEndpoints(
        uf="SP",
        tp_amb=tp_amb,
        autorizacao=f"{base}/NFeAutorizacao4.asmx",
        ret_autorizacao=f"{base}/NFeRetAutorizacao4.asmx",
        consulta_protocolo=f"{base}/NFeConsultaProtocolo4.asmx",
        recepcao_evento=f"{base}/NFeRecepcaoEvento4.asmx",
        status_servico=f"{base}/NFeStatusServico4.asmx",
        qr_base_url=qr,
    )


_CATALOG: dict[tuple[str, str], SefazNfceEndpoints] = {
    ("SP", "2"): _sp("2"),
    ("SP", "1"): _sp("1"),
}


def list_supported_nfce_ufs() -> list[str]:
    return ["SP"]


def resolve_nfce_endpoints(*, uf: str = "SP", tp_amb: str = "2") -> SefazNfceEndpoints:
    code = (uf or "SP").upper().strip()
    amb = str(tp_amb or "2").strip()[:1] or "2"
    if amb not in {"1", "2"}:
        amb = "2"
    ep = _CATALOG.get((code, amb))
    if ep is None:
        raise ValueError(
            f"NFC-e UF {code} fora do catálogo pivot (suportada: {', '.join(list_supported_nfce_ufs())})"
        )
    return ep


def as_nfe_endpoints(ep: SefazNfceEndpoints) -> SefazNfeEndpoints:
    """Adapter para transport compartilhado (mesmo SOAP NFeAutorizacao4)."""
    return SefazNfeEndpoints(
        uf=ep.uf,
        tp_amb=ep.tp_amb,
        autorizacao=ep.autorizacao,
        ret_autorizacao=ep.ret_autorizacao,
        consulta_protocolo=ep.consulta_protocolo,
        recepcao_evento=ep.recepcao_evento,
        status_servico=ep.status_servico,
        authority=ep.uf,
    )
