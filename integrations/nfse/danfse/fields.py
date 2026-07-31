"""Extrai campos do DANFSe somente a partir das tags do XML da NFS-e (RF-41b)."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree as ET

from integrations.nfse.xml_safe import safe_fromstring

QR_BASE_URL = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave="


@dataclass(frozen=True)
class DanfseFields:
    municipio_emitente: str
    ambiente: str
    ambiente_codigo: str  # "1" | "2"
    numero: str
    chave_acesso: str
    data_emissao: str
    competencia: str
    numero_dps: str
    serie_dps: str
    data_emissao_dps: str
    emitente_nfse: str
    situacao: str
    finalidade: str
    prestador_nome: str
    prestador_doc: str
    prestador_im: str
    prestador_municipio: str
    prestador_endereco: str
    tomador_nome: str
    tomador_doc: str
    tomador_im: str
    tomador_endereco: str
    descricao_servico: str
    codigo_servico: str
    local_prestacao: str
    valor_servico: str
    valor_iss: str
    valor_liquido: str
    approx_federais: str
    approx_estaduais: str
    approx_municipais: str
    approx_sn_percent: str
    cancelled: bool
    qr_payload: str

    @property
    def is_homologacao(self) -> bool:
        return self.ambiente_codigo == "2" or self.ambiente.lower().startswith("homolog")


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split()).strip()


def _first(root: ET.Element, *names: str) -> ET.Element | None:
    wanted = {n.lower() for n in names}
    for el in root.iter():
        if _local(el.tag).lower() in wanted and (_text(el) or list(el)):
            return el
    return None


def _first_text(root: ET.Element, *names: str) -> str:
    return _text(_first(root, *names))


def _child_text(parent: ET.Element | None, *names: str) -> str:
    if parent is None:
        return ""
    wanted = {n.lower() for n in names}
    for child in parent:
        if _local(child.tag).lower() in wanted:
            return _text(child)
    return ""


def _find_child(parent: ET.Element | None, *names: str) -> ET.Element | None:
    if parent is None:
        return None
    wanted = {n.lower() for n in names}
    for child in parent:
        if _local(child.tag).lower() in wanted:
            return child
    return None


def _format_endereco(block: ET.Element | None) -> str:
    """Monta endereço a partir de enderNac / end / endNac (somente tags do XML)."""
    if block is None:
        return ""
    end = _find_child(block, "enderNac", "end", "endereco", "ender")
    if end is None:
        end = block
    nested = _find_child(end, "endNac", "enderNac")

    def pick(*names: str) -> str:
        return _child_text(nested, *names) or _child_text(end, *names) or _child_text(block, *names)

    parts = [
        pick("xLgr", "logradouro"),
        pick("nro", "numero"),
        pick("xBairro", "bairro"),
        pick("xMun", "municipio") or pick("cMun"),
        pick("UF", "uf"),
        pick("CEP", "cep"),
    ]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) > 1 and parts[1].replace("-", "").isdigit() and not parts[0].replace("-", "").isdigit():
        line = f"{parts[0]}, {parts[1]}"
        rest = parts[2:]
    else:
        line = parts[0]
        rest = parts[1:]
    if rest:
        line = f"{line} — {' / '.join(rest)}"
    return line


def _cstat_label(code: str) -> str:
    mapping = {
        "100": "Autorizada",
        "101": "Cancelada",
        "102": "Substituída",
    }
    return mapping.get(code, code or "—")


def extract_danfse_fields(xml_bytes: bytes, *, cancelled: bool = False) -> DanfseFields:
    root = safe_fromstring(xml_bytes)
    inf = _first(root, "infNFSe", "InfNfse")
    if inf is None:
        inf = root
    emit = _first(root, "emit", "prest", "prestador")
    # Prefer tomador da NFS-e; fallback DPS (layout SEFIN prod).
    toma = _first(root, "toma", "tomador")
    valores = _first(root, "valores", "valoresnfse")
    serv = _first(root, "serv", "servico", "cServ")

    chave = (
        _first_text(root, "chNFSe", "chaveAcesso", "chave")
        or (inf.attrib.get("Id") or "").removeprefix("NFS")
        or _first_text(root, "Id")
    )
    numero = _first_text(root, "nNFSe", "numero")
    municipio = (
        _first_text(root, "xLocEmi", "xMun", "municipio")
        or _first_text(root, "xLocIncid")
    )
    ambiente_raw = _first_text(root, "tpAmb", "ambiente").strip()
    ambiente_codigo = ambiente_raw if ambiente_raw in {"1", "2"} else (
        "2" if ambiente_raw.lower() in {"hom", "homolog", "homologacao", "homologação"} else
        "1" if ambiente_raw.lower() in {"prod", "producao", "produção"} else "2"
    )
    ambiente = "Produção" if ambiente_codigo == "1" else "Homologação"

    cstat = _first_text(root, "cStat", "status")
    cancelled_flag = cancelled or cstat.upper() in {"CANCELADA", "101"}

    valor_servico = (
        _child_text(valores, "vServReceb", "vServ", "valor")
        or _first_text(root, "vServReceb", "vServ")
    )
    valor_iss = (
        _child_text(valores, "vISSQN", "vIss", "valorIss")
        or _first_text(root, "vISSQN", "vIss")
    )
    valor_liquido = (
        _child_text(valores, "vLiq", "valorLiquido")
        or _first_text(root, "vLiq")
        or valor_servico
    )
    codigo = (
        _child_text(serv, "cTribNac", "cServ", "codigo")
        or _first_text(root, "cTribNac", "codigoTributacaoNacional")
    )
    descricao = (
        _child_text(serv, "xDescServ", "xServ", "discriminacao", "descricao")
        or _first_text(root, "xDescServ", "discriminacao")
        or _first_text(root, "xTribNac")
    )
    local_prestacao = (
        _first_text(root, "xLocPrestacao")
        or _first_text(root, "cLocPrestacao", "xLocPrestacao")
        or municipio
    )

    approx_sn = _first_text(root, "pTotTribSN")
    approx_fed = _first_text(root, "vTotTribFed", "tribApproxFed")
    approx_est = _first_text(root, "vTotTribEst", "tribApproxEst")
    approx_mun = _first_text(root, "vTotTribMun", "tribApproxMun")

    qr_payload = f"{QR_BASE_URL}{chave}" if chave else "https://www.nfse.gov.br/ConsultaPublica/"

    prest_end = _format_endereco(emit)
    toma_end = _format_endereco(toma)

    return DanfseFields(
        municipio_emitente=municipio or "—",
        ambiente=ambiente,
        ambiente_codigo=ambiente_codigo,
        numero=numero or "—",
        chave_acesso=chave or "—",
        data_emissao=_first_text(root, "dhProc", "dhEmi", "dataEmissao") or "—",
        competencia=_first_text(root, "dCompet", "competencia") or "—",
        numero_dps=_first_text(root, "nDPS", "numeroDPS") or "—",
        serie_dps=_first_text(root, "serie", "serieDPS") or "—",
        data_emissao_dps=_first_text(root, "dhDPS", "dhEmi") or "—",
        emitente_nfse=_first_text(root, "cMotivoEmit", "emitente")
        or _child_text(emit, "xNome")
        or "Prestador",
        situacao="Cancelada" if cancelled_flag else _cstat_label(cstat),
        finalidade=_first_text(root, "finNFSe", "finalidade") or "Normal",
        prestador_nome=_child_text(emit, "xNome", "razaoSocial", "nome") or "—",
        prestador_doc=_child_text(emit, "CNPJ", "CPF", "cnpj", "cpf") or "—",
        prestador_im=_child_text(emit, "IM", "inscricaoMunicipal") or "—",
        prestador_municipio=_child_text(emit, "xMun", "cMun") or municipio or "—",
        prestador_endereco=prest_end or "—",
        tomador_nome=_child_text(toma, "xNome", "razaoSocial", "nome") or "—",
        tomador_doc=_child_text(toma, "CNPJ", "CPF", "cnpj", "cpf") or "—",
        tomador_im=_child_text(toma, "IM", "inscricaoMunicipal") or "",
        tomador_endereco=toma_end or "",
        descricao_servico=descricao or "—",
        codigo_servico=codigo or "—",
        local_prestacao=local_prestacao or "—",
        valor_servico=valor_servico or "—",
        valor_iss=valor_iss or "—",
        valor_liquido=valor_liquido or "—",
        approx_federais=approx_fed or "",
        approx_estaduais=approx_est or "",
        approx_municipais=approx_mun or "",
        approx_sn_percent=approx_sn or "",
        cancelled=cancelled_flag,
        qr_payload=qr_payload,
    )
