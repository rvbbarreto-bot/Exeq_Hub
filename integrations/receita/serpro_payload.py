"""Montagem/parse do envelope Integra Contador (PGDASD / GERARDAS12)."""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any

from integrations.receita.exceptions import ReceitaBusinessError
from integrations.receita.port import GuiaCapturaResult


def competencia_to_periodo(competencia: str) -> str:
    """AAAA-MM → AAAAMM."""
    digits = "".join(ch for ch in competencia if ch.isdigit())
    if len(digits) != 6:
        raise ReceitaBusinessError(f"Competência inválida: {competencia}")
    return digits


def periodo_to_iso_date(yyyymmdd: str | None) -> str | None:
    if not yyyymmdd:
        return None
    digits = "".join(ch for ch in str(yyyymmdd) if ch.isdigit())
    if len(digits) != 8:
        return None
    return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"


def build_person(*, cnpj: str) -> dict[str, Any]:
    digits = "".join(ch for ch in cnpj if ch.isdigit())
    return {"numero": digits, "tipo": 2}


def build_gerar_das_envelope(
    *,
    cnpj: str,
    competencia: str,
    id_sistema: str,
    id_servico: str,
    versao_sistema: str,
    data_consolidacao: str | None = None,
) -> dict[str, Any]:
    periodo = competencia_to_periodo(competencia)
    dados_obj: dict[str, str] = {"periodoApuracao": periodo}
    if data_consolidacao:
        dados_obj["dataConsolidacao"] = "".join(
            ch for ch in data_consolidacao if ch.isdigit()
        )
    person = build_person(cnpj=cnpj)
    return {
        "contratante": person,
        "autorPedidoDados": person,
        "contribuinte": person,
        "pedidoDados": {
            "idSistema": id_sistema,
            "idServico": id_servico,
            "versaoSistema": versao_sistema,
            "dados": json.dumps(dados_obj, separators=(",", ":")),
        },
    }


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _first_das_item(dados: Any) -> dict[str, Any]:
    if isinstance(dados, str):
        dados = json.loads(dados)
    if isinstance(dados, list):
        if not dados:
            raise ReceitaBusinessError("SERPRO retornou lista DAS vazia")
        item = dados[0]
    elif isinstance(dados, dict):
        # alguns retornos encapsulam em {"listaDas": [...]} ou similar
        for key in ("listaDas", "das", "itens", "lista"):
            nested = dados.get(key)
            if isinstance(nested, list) and nested:
                item = nested[0]
                break
        else:
            item = dados
    else:
        raise ReceitaBusinessError("Formato de dados DAS não reconhecido")
    if not isinstance(item, dict):
        raise ReceitaBusinessError("Item DAS inválido")
    return item


def map_gerar_das_response(payload: dict[str, Any]) -> GuiaCapturaResult:
    """Mapeia resposta Emitir/GERARDAS12 → GuiaCapturaResult."""
    mensagens = payload.get("mensagens") or []
    status_http = payload.get("status")
    if status_http is not None and int(status_http) >= 400:
        texts = []
        for msg in mensagens:
            if isinstance(msg, dict):
                texts.append(f"{msg.get('codigo', '')}:{msg.get('texto', msg)}")
            else:
                texts.append(str(msg))
        raise ReceitaBusinessError(
            "SERPRO rejeitou GERARDAS12: " + ("; ".join(texts) or str(payload))
        )

    if payload.get("dados") in (None, ""):
        texts = [
            f"{m.get('codigo', '')}:{m.get('texto', m)}"
            if isinstance(m, dict)
            else str(m)
            for m in mensagens
        ]
        raise ReceitaBusinessError(
            "SERPRO sem dados de DAS: " + ("; ".join(texts) or "resposta vazia")
        )

    item = _first_das_item(payload.get("dados"))
    detalhe = item.get("detalhamento") or {}
    valores = detalhe.get("valores") or item.get("valores") or {}
    pdf_b64 = item.get("pdf") or ""
    pdf_bytes = b""
    if pdf_b64:
        try:
            pdf_bytes = base64.b64decode(pdf_b64)
        except Exception as exc:  # noqa: BLE001
            raise ReceitaBusinessError("PDF DAS base64 inválido") from exc

    due = periodo_to_iso_date(detalhe.get("dataVencimento") or item.get("dataVencimento"))
    motivo_parts = []
    for msg in mensagens:
        if isinstance(msg, dict):
            motivo_parts.append(str(msg.get("texto") or msg.get("codigo") or msg))
        else:
            motivo_parts.append(str(msg))

    return GuiaCapturaResult(
        valor_principal=_as_decimal(valores.get("principal")),
        valor_multa=_as_decimal(valores.get("multa")),
        valor_juros=_as_decimal(valores.get("juros")),
        linha_digitavel=str(
            item.get("linhaDigitavel")
            or detalhe.get("linhaDigitavel")
            or item.get("codigoBarras")
            or ""
        ),
        pix_copia_cola=str(
            item.get("pixCopiaCola") or detalhe.get("pixCopiaCola") or ""
        ),
        compliance_status="aprovado",
        compliance_motivo="; ".join(motivo_parts) or "serpro_ok",
        data_vencimento=due,
        pdf_bytes=pdf_bytes,
        raw={
            "provider": "serpro",
            "mode": "http",
            "idServico": "GERARDAS12",
            "numeroDocumento": detalhe.get("numeroDocumento"),
            "mensagens": mensagens,
            "status": status_http,
            "detalhamento": detalhe,
        },
    )
