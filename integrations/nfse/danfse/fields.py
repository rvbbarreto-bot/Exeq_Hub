"""Extrai campos do DANFSe somente a partir das tags do XML da NFS-e (RF-41b)."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree as ET

from integrations.nfse.danfse.labels import (
    label_amb_gerador,
    label_emitente,
    label_finalidade,
    label_op_simp_nac,
    label_reg_ap_trib_sn,
    label_reg_esp_trib,
    label_situacao,
    label_trib_issqn,
    label_tp_ret_issqn,
)
from integrations.nfse.xml_safe import safe_fromstring

QR_BASE_URL = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave="


@dataclass(frozen=True)
class DanfseFields:
    municipio_emitente: str
    ambiente: str
    ambiente_codigo: str
    ver_aplic: str
    amb_gerador: str
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
    prestador_uf: str
    prestador_cmun: str
    prestador_cep: str
    prestador_endereco: str
    prestador_fone: str
    prestador_email: str
    op_simp_nac: str
    reg_ap_trib_sn: str
    reg_esp_trib: str
    tomador_nome: str
    tomador_doc: str
    tomador_im: str
    tomador_endereco: str
    tomador_municipio: str
    tomador_uf: str
    tomador_cmun: str
    tomador_cep: str
    tomador_email: str
    destinatario_nome: str
    intermediario_nome: str
    descricao_servico: str
    codigo_servico: str
    codigo_trib_municipal: str
    codigo_nbs: str
    x_trib_nac: str
    local_prestacao: str
    local_prestacao_uf: str
    local_prestacao_pais: str
    municipio_incidencia: str
    trib_issqn: str
    tp_ret_issqn: str
    iss_bc: str
    iss_aliquota: str
    iss_valor: str
    irrf: str
    inss: str
    pis: str
    cofins: str
    csll: str
    cst_ibs_cbs: str
    c_class_trib: str
    c_ind_op: str
    ibs_bc: str
    ibs_aliq_uf: str
    ibs_aliq_mun: str
    ibs_valor: str
    cbs_bc: str
    cbs_aliquota: str
    cbs_valor: str
    valor_servico: str
    valor_deducoes: str
    desconto_incond: str
    desconto_cond: str
    valor_iss: str
    valor_iss_retido: str
    valor_liquido: str
    approx_federais: str
    approx_estaduais: str
    approx_municipais: str
    approx_sn_percent: str
    informacoes_complementares: str
    cancelled: bool
    qr_payload: str

    @property
    def is_homologacao(self) -> bool:
        return self.ambiente_codigo == "2" or self.ambiente.lower().startswith("homolog")

    @property
    def has_destinatario(self) -> bool:
        return self.destinatario_nome not in {"", "—"}

    @property
    def has_intermediario(self) -> bool:
        return self.intermediario_nome not in {"", "—"}


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


def _service_c_serv(serv: ET.Element | None) -> ET.Element | None:
    """Bloco cServ dentro de serv (layout DPS) ou o próprio cServ."""
    if serv is None:
        return None
    if _local(serv.tag).lower() == "cserv":
        return serv
    return _find_child(serv, "cServ")


def _dps_inf(root: ET.Element) -> ET.Element | None:
    dps = _first(root, "DPS")
    if dps is None:
        return None
    inf_dps = _find_child(dps, "infDPS")
    return inf_dps if inf_dps is not None else dps


def _dps_valores(root: ET.Element) -> ET.Element | None:
    inf = _dps_inf(root)
    if inf is not None:
        return _find_child(inf, "valores")
    return _first(root, "valores", "valoresnfse")


def _trib_block(root: ET.Element) -> ET.Element | None:
    valores = _dps_valores(root)
    if valores is not None:
        trib = _find_child(valores, "trib")
        if trib is not None:
            return trib
    return _first(root, "trib")


def _format_endereco(block: ET.Element | None) -> str:
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


def _endereco_mun_uf(block: ET.Element | None) -> tuple[str, str]:
    if block is None:
        return "", ""
    end = _find_child(block, "enderNac", "end", "endereco", "ender")
    if end is None:
        end = block
    nested = _find_child(end, "endNac", "enderNac")
    mun = _child_text(nested, "xMun", "cMun") or _child_text(end, "xMun", "cMun")
    uf = _child_text(nested, "UF", "uf") or _child_text(end, "UF", "uf")
    return mun, uf


def _pick_money(*values: str) -> str:
    for v in values:
        if v and v not in {"—", "-"}:
            return v
    return ""


def extract_danfse_fields(xml_bytes: bytes, *, cancelled: bool = False) -> DanfseFields:
    root = safe_fromstring(xml_bytes)
    inf = _first(root, "infNFSe", "InfNfse")
    if inf is None:
        inf = root
    dps_inf = _dps_inf(root)
    emit = _first(root, "emit", "prest", "prestador")
    toma = _first(root, "toma", "tomador")
    dest = _first(root, "dest", "destinatario")
    interm = _first(root, "interm", "intermediario")
    valores_nfse = _find_child(inf, "valores") if inf is not root else _first(root, "valores")
    valores_dps = _dps_valores(root)
    trib = _trib_block(root)
    trib_mun = _find_child(trib, "tribMun")
    trib_fed = _find_child(trib, "tribFed")
    tot_trib = _find_child(trib, "totTrib")
    reg_trib = _find_child(emit, "regTrib") or _find_child(
        _first(root, "prest", "prestador"), "regTrib"
    )
    serv = _first(root, "serv", "servico", "cServ")
    c_serv = _service_c_serv(serv)
    loc_prest = _find_child(serv, "locPrest") if serv is not None else _first(root, "locPrest")
    ibscbs = _first(root, "gIBSCBS", "IBSCBS", "gIBSCBSMono")

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
    ambiente_raw = (
        _child_text(dps_inf, "tpAmb")
        or _first_text(root, "tpAmb", "ambiente")
    ).strip()
    ambiente_codigo = ambiente_raw if ambiente_raw in {"1", "2"} else (
        "2" if ambiente_raw.lower() in {"hom", "homolog", "homologacao", "homologação"} else
        "1" if ambiente_raw.lower() in {"prod", "producao", "produção"} else "2"
    )
    ambiente = "Produção" if ambiente_codigo == "1" else "Homologação"

    cstat = _first_text(root, "cStat", "status")
    cancelled_flag = cancelled or cstat.upper() in {"CANCELADA", "101"}

    v_serv_prest = _find_child(valores_dps, "vServPrest")
    valor_servico = _pick_money(
        _child_text(v_serv_prest, "vServ"),
        _child_text(valores_nfse, "vServReceb", "vServ", "valor"),
        _first_text(root, "vServReceb", "vServ"),
    )
    valor_iss = _pick_money(
        _child_text(trib_mun, "vISSQN", "vIss"),
        _child_text(valores_nfse, "vISSQN", "vIss", "valorIss"),
        _first_text(root, "vISSQN", "vIss"),
    )
    valor_liquido = _pick_money(
        _child_text(valores_nfse, "vLiq", "valorLiquido"),
        _child_text(valores_dps, "vLiq"),
        _first_text(root, "vLiq"),
        valor_servico,
    )
    codigo = (
        _child_text(c_serv, "cTribNac")
        or _child_text(serv, "cTribNac", "cServ", "codigo")
        or _first_text(root, "cTribNac", "codigoTributacaoNacional")
    )
    cod_trib_mun = (
        _child_text(c_serv, "cTribMun", "cTribMunicipal")
        or _child_text(serv, "cTribMun", "cTribMunicipal")
        or _first_text(root, "cTribMun")
    )
    cod_nbs = (
        _child_text(c_serv, "cNBS", "cNbs")
        or _child_text(serv, "cNBS", "cNbs")
        or _first_text(root, "cNBS", "cNbs")
    )
    x_trib_nac = _first_text(root, "xTribNac")
    descricao = (
        _child_text(c_serv, "xDescServ", "xServ", "discriminacao", "descricao")
        or _child_text(serv, "xDescServ", "xServ", "discriminacao", "descricao")
        or _first_text(root, "xDescServ", "discriminacao")
        or x_trib_nac
    )
    info_compl = (
        _child_text(serv, "xInfComp")
        or _first_text(root, "xInfComp")
    )
    local_prestacao = (
        _first_text(root, "xLocPrestacao")
        or _child_text(loc_prest, "xLocPrestacao")
        or _first_text(root, "cLocPrestacao")
        or municipio
    )
    local_uf = _child_text(loc_prest, "UF") or _first_text(root, "UF")
    local_pais = _child_text(loc_prest, "cPais", "xPais") or _first_text(root, "cPais") or "1058"
    municipio_incidencia = _first_text(root, "xLocIncid") or municipio

    approx_sn = _child_text(tot_trib, "pTotTribSN") or _first_text(root, "pTotTribSN")
    approx_fed = (
        _child_text(tot_trib, "vTotTribFed")
        or _first_text(root, "vTotTribFed", "tribApproxFed")
    )
    approx_est = (
        _child_text(tot_trib, "vTotTribEst")
        or _first_text(root, "vTotTribEst", "tribApproxEst")
    )
    approx_mun = (
        _child_text(tot_trib, "vTotTribMun")
        or _first_text(root, "vTotTribMun", "tribApproxMun")
    )

    op_simp_raw = _child_text(reg_trib, "opSimpNac")
    reg_ap_sn_raw = _child_text(reg_trib, "regApTribSN")
    reg_esp_raw = _child_text(reg_trib, "regEspTrib")

    trib_issqn_raw = _child_text(trib_mun, "tribISSQN")
    tp_ret_raw = _child_text(trib_mun, "tpRetISSQN")

    iss_bc = _child_text(trib_mun, "vBC", "vBc")
    iss_aliq = _child_text(trib_mun, "pAliq", "pAliqAplic")
    iss_retido = _child_text(trib_mun, "vISSRet", "vIssRet")

    irrf = _child_text(trib_fed, "vRetIRRF", "vIRRF")
    inss = _child_text(trib_fed, "vRetCP", "vINSS", "vRetINSS")
    pis = _child_text(trib_fed, "vRetPIS", "vPIS")
    cofins = _child_text(trib_fed, "vRetCOFINS", "vCOFINS")
    csll = _child_text(trib_fed, "vRetCSLL", "vCSLL")

    cst = _child_text(ibscbs, "CST") or _first_text(root, "CST")
    c_class = _child_text(ibscbs, "cClassTrib") or _first_text(root, "cClassTrib")
    c_ind = _child_text(ibscbs, "cIndOp") or _first_text(root, "cIndOp")
    ibs_grp = _find_child(ibscbs, "gIBSCBS") or ibscbs
    ibs_bc = _child_text(ibs_grp, "vBC")
    ibs_aliq_uf = _child_text(ibs_grp, "pIBSUF", "pAliqIBSUF")
    ibs_aliq_mun = _child_text(ibs_grp, "pIBSMun", "pAliqIBSMun")
    ibs_valor = _pick_money(
        _child_text(ibs_grp, "vIBS"),
        _child_text(ibs_grp, "vIBSUF"),
    )
    cbs_bc = ibs_bc or _child_text(ibscbs, "vBCCBS")
    cbs_aliq = _child_text(ibs_grp, "pCBS", "pAliqCBS")
    cbs_valor = _child_text(ibs_grp, "vCBS")

    deducoes = _child_text(valores_dps, "vDedRed", "vDeducao") or _child_text(valores_nfse, "vDedRed")
    desc_incond = _child_text(valores_dps, "vDescIncond") or _child_text(valores_nfse, "vDescIncond")
    desc_cond = _child_text(valores_dps, "vDescCond") or _child_text(valores_nfse, "vDescCond")

    prest_end = _format_endereco(emit)
    toma_end = _format_endereco(toma)
    toma_mun, toma_uf = _endereco_mun_uf(toma)
    emit_end = _find_child(emit, "enderNac", "end") if emit is not None else None
    toma_end_el = _find_child(toma, "end", "enderNac") if toma is not None else None
    toma_nac = _find_child(toma_end_el, "endNac", "enderNac") if toma_end_el is not None else None
    prest_mun = _child_text(emit, "xMun", "cMun") or municipio
    prest_uf = _child_text(emit_end, "UF") or _first_text(root, "UF")
    prest_cmun = _child_text(emit_end, "cMun") or ""
    prest_cep = _child_text(emit_end, "CEP", "cep") or ""
    toma_cmun = _child_text(toma_nac, "cMun") or _child_text(toma_end_el, "cMun") or toma_mun
    toma_cep = _child_text(toma_nac, "CEP", "cep") or _child_text(toma_end_el, "CEP") or ""

    fin_raw = _first_text(root, "finNFSe", "finalidade")
    tp_emit = _child_text(dps_inf, "tpEmit") or _first_text(root, "tpEmit", "cMotivoEmit")

    qr_payload = f"{QR_BASE_URL}{chave}" if chave else "https://www.nfse.gov.br/ConsultaPublica/"

    return DanfseFields(
        municipio_emitente=municipio or "—",
        ambiente=ambiente,
        ambiente_codigo=ambiente_codigo,
        ver_aplic=_first_text(root, "verAplic") or _child_text(dps_inf, "verAplic") or "—",
        amb_gerador=label_amb_gerador(_first_text(root, "ambGer")),
        numero=numero or "—",
        chave_acesso=chave or "—",
        data_emissao=_first_text(root, "dhProc", "dhEmi", "dataEmissao") or "—",
        competencia=_child_text(dps_inf, "dCompet") or _first_text(root, "dCompet", "competencia") or "—",
        numero_dps=_child_text(dps_inf, "nDPS") or _first_text(root, "nDPS", "numeroDPS") or "—",
        serie_dps=_child_text(dps_inf, "serie") or _first_text(root, "serie", "serieDPS") or "—",
        data_emissao_dps=_child_text(dps_inf, "dhEmi") or _first_text(root, "dhDPS", "dhEmi") or "—",
        emitente_nfse=label_emitente(tp_emit),
        situacao=label_situacao(cstat, cancelled=cancelled_flag),
        finalidade=label_finalidade(fin_raw),
        prestador_nome=_child_text(emit, "xNome", "razaoSocial", "nome") or "—",
        prestador_doc=_child_text(emit, "CNPJ", "CPF", "cnpj", "cpf") or "—",
        prestador_im=_child_text(emit, "IM", "inscricaoMunicipal") or "—",
        prestador_municipio=prest_mun or "—",
        prestador_uf=prest_uf or "",
        prestador_cmun=prest_cmun or "",
        prestador_cep=prest_cep or "",
        prestador_endereco=prest_end or "—",
        prestador_fone=_child_text(emit, "fone", "telefone") or "",
        prestador_email=_child_text(emit, "email") or "",
        op_simp_nac=label_op_simp_nac(op_simp_raw),
        reg_ap_trib_sn=label_reg_ap_trib_sn(reg_ap_sn_raw) if reg_ap_sn_raw else "",
        reg_esp_trib=label_reg_esp_trib(reg_esp_raw or "0"),
        tomador_nome=_child_text(toma, "xNome", "razaoSocial", "nome") or "—",
        tomador_doc=_child_text(toma, "CNPJ", "CPF", "cnpj", "cpf") or "—",
        tomador_im=_child_text(toma, "IM", "inscricaoMunicipal") or "",
        tomador_endereco=toma_end or "",
        tomador_municipio=toma_mun,
        tomador_uf=toma_uf,
        tomador_cmun=toma_cmun or "",
        tomador_cep=toma_cep or "",
        tomador_email=_child_text(toma, "email") or "",
        destinatario_nome=_child_text(dest, "xNome") if dest else "",
        intermediario_nome=_child_text(interm, "xNome") if interm else "",
        descricao_servico=descricao or "—",
        codigo_servico=codigo or "—",
        codigo_trib_municipal=cod_trib_mun or "",
        codigo_nbs=cod_nbs or "",
        x_trib_nac=x_trib_nac or "",
        local_prestacao=local_prestacao or "—",
        local_prestacao_uf=local_uf or "",
        local_prestacao_pais=local_pais,
        municipio_incidencia=municipio_incidencia or "—",
        trib_issqn=label_trib_issqn(trib_issqn_raw),
        tp_ret_issqn=label_tp_ret_issqn(tp_ret_raw),
        iss_bc=iss_bc or "",
        iss_aliquota=iss_aliq or "",
        iss_valor=valor_iss or "",
        irrf=irrf or "",
        inss=inss or "",
        pis=pis or "",
        cofins=cofins or "",
        csll=csll or "",
        cst_ibs_cbs=cst or "",
        c_class_trib=c_class or "",
        c_ind_op=c_ind or "",
        ibs_bc=ibs_bc or "",
        ibs_aliq_uf=ibs_aliq_uf or "",
        ibs_aliq_mun=ibs_aliq_mun or "",
        ibs_valor=ibs_valor or "",
        cbs_bc=cbs_bc or "",
        cbs_aliquota=cbs_aliq or "",
        cbs_valor=cbs_valor or "",
        valor_servico=valor_servico or "—",
        valor_deducoes=deducoes or "",
        desconto_incond=desc_incond or "",
        desconto_cond=desc_cond or "",
        valor_iss=valor_iss or "—",
        valor_iss_retido=iss_retido or "",
        valor_liquido=valor_liquido or "—",
        approx_federais=approx_fed or "",
        approx_estaduais=approx_est or "",
        approx_municipais=approx_mun or "",
        approx_sn_percent=approx_sn or "",
        informacoes_complementares=info_compl or "",
        cancelled=cancelled_flag,
        qr_payload=qr_payload,
    )
