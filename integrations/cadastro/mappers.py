"""Mapeia respostas de provedores HTTP → CadastralLookupResult."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from integrations.cadastro.port import CadastralAddress, CadastralLookupResult


def _s(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: Any) -> date | None:
    text = _s(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _fmt_cnae(codigo: Any, descricao: Any) -> str:
    code = _s(codigo).replace(".0", "")
    desc = _s(descricao)
    if code and desc:
        return f"{code} - {desc}"
    return code or desc


def _cep(value: Any) -> str:
    digits = "".join(ch for ch in _s(value) if ch.isdigit())
    return digits[:8]


def map_brasilapi_cnpj(payload: dict[str, Any], *, cnpj: str, provider_kind: str) -> CadastralLookupResult:
    natureza = _s(payload.get("natureza_juridica"))
    if not natureza and payload.get("codigo_natureza_juridica") is not None:
        natureza = _s(payload.get("codigo_natureza_juridica"))

    secundarios: list[str] = []
    for item in payload.get("cnaes_secundarios") or []:
        if isinstance(item, dict):
            line = _fmt_cnae(item.get("codigo"), item.get("descricao"))
            if line:
                secundarios.append(line)

    porte = _s(payload.get("descricao_porte")) or _s(payload.get("porte"))
    situacao = _s(payload.get("descricao_situacao_cadastral")) or _s(
        payload.get("situacao_cadastral")
    )

    tipo_log = _s(payload.get("descricao_tipo_logradouro"))
    logradouro = _s(payload.get("logradouro"))
    if tipo_log and logradouro and not logradouro.lower().startswith(tipo_log.lower()):
        logradouro = f"{tipo_log} {logradouro}".strip()

    telefone = _s(payload.get("ddd_telefone_1") or payload.get("telefone"))
    email = _s(payload.get("email") or payload.get("correio_eletronico"))

    return CadastralLookupResult(
        document=cnpj,
        legal_name=_s(payload.get("razao_social")) or _s(payload.get("nome")),
        trade_name=_s(payload.get("nome_fantasia")),
        situacao_cadastral=situacao,
        data_abertura=_parse_date(
            payload.get("data_inicio_atividade") or payload.get("data_abertura")
        ),
        natureza_juridica=natureza,
        cnae_principal=_fmt_cnae(
            payload.get("cnae_fiscal"), payload.get("cnae_fiscal_descricao")
        ),
        cnaes_secundarios=secundarios,
        porte=porte,
        optante_simples=payload.get("opcao_pelo_simples"),
        optante_mei=payload.get("opcao_pelo_mei"),
        telefone=telefone,
        email=email,
        address=CadastralAddress(
            logradouro=logradouro,
            numero=_s(payload.get("numero")),
            complemento=_s(payload.get("complemento")),
            bairro=_s(payload.get("bairro")),
            cep=_cep(payload.get("cep")),
            municipio=_s(payload.get("municipio")),
            uf=_s(payload.get("uf")),
            codigo_municipio_ibge=_s(
                payload.get("codigo_municipio_ibge") or payload.get("codigo_municipio")
            ),
        ),
        raw=payload,
        provider_kind=provider_kind,
    )
