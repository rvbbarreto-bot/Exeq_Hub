from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.issuance.models import NfIssue
from apps.master_data.models import Customer, TaxRegime


def to_focus_nfse(issue: NfIssue) -> dict[str, Any]:
    """JSON aninhado Focus municipal POST /v2/nfse."""
    provider = issue.provider
    customer = issue.customer
    service = issue.service
    params = issue.resolved_params or {}
    amount = (Decimal(issue.amount_cents) / Decimal(100)).quantize(Decimal("0.01"))
    iss_rate = Decimal(str(params.get("iss_rate") or "0"))
    aliquota = (iss_rate * Decimal(100)).quantize(Decimal("0.0001"))
    iss_retained = bool(params.get("iss_retained", False))
    item_lista = service.lc116_item or service.service_code

    body: dict[str, Any] = {
        "data_emissao": issue.competence_date.isoformat(),
        "natureza_operacao": "1",
        "optante_simples_nacional": provider.tax_regime == TaxRegime.SIMPLES,
        "prestador": {
            "cnpj": provider.document,
            "inscricao_municipal": provider.municipal_registration or "",
            "codigo_municipio": issue.ibge_code,
        },
        "tomador": _tomador_nested(customer, fallback_ibge=issue.ibge_code),
        "servico": {
            "valor_servicos": float(amount),
            "iss_retido": iss_retained,
            "item_lista_servico": item_lista,
            "discriminacao": service.description,
            "codigo_municipio": issue.ibge_code,
            "aliquota": float(aliquota),
        },
    }
    return _apply_overrides(issue, body)


def to_focus_nfsen(issue: NfIssue) -> dict[str, Any]:
    """JSON plano Focus NFS-e Nacional POST /v2/nfsen (layout Atibaia/Nacional)."""
    provider = issue.provider
    customer = issue.customer
    service = issue.service
    params = issue.resolved_params or {}
    amount = (Decimal(issue.amount_cents) / Decimal(100)).quantize(Decimal("0.01"))
    iss_rate = Decimal(str(params.get("iss_rate") or "0"))
    aliquota = float((iss_rate * Decimal(100)).quantize(Decimal("0.0001")))
    codigo_trib = (
        params.get("codigo_tributacao_nacional_iss")
        or service.codigo_tributacao_nacional_iss
        or service.lc116_item
        or service.service_code
    )
    iss_retained = bool(params.get("iss_retained", False))
    # 1=não retido · 2=retido tomador · 3=retido intermediário (tpRetISSQN / tribMun)
    tipo_retencao = int(params.get("tipo_retencao_iss") or (2 if iss_retained else 1))

    body: dict[str, Any] = {
        "data_emissao": f"{issue.competence_date.isoformat()}T12:00:00-0300",
        "data_competencia": issue.competence_date.isoformat(),
        "codigo_municipio_emissora": issue.ibge_code,
        "cnpj_prestador": provider.document,
        "codigo_opcao_simples_nacional": _simples_option(provider.tax_regime),
        "regime_tributario_simples_nacional": (
            1 if provider.tax_regime == TaxRegime.SIMPLES else 3
        ),
        "regime_especial_tributacao": int(
            params.get("regime_especial_tributacao")
            if params.get("regime_especial_tributacao") is not None
            else 0
        ),
        "codigo_municipio_prestacao": issue.ibge_code,
        "codigo_tributacao_nacional_iss": str(codigo_trib),
        "descricao_servico": service.description,
        "valor_servico": float(amount),
        "tributacao_iss": int(params.get("tributacao_iss") or 1),
        "tipo_retencao_iss": tipo_retencao,
    }
    # SEFIN E0625: ME/EPP SN (opSimpNac=3) sem retenção não informa alíquota
    if tipo_retencao != 1 or body["codigo_opcao_simples_nacional"] != 3:
        body["percentual_aliquota_relativa_municipio"] = aliquota
    elif params.get("percentual_aliquota_relativa_municipio") is not None:
        body["percentual_aliquota_relativa_municipio"] = float(
            params["percentual_aliquota_relativa_municipio"]
        )
    # SEFIN E0712: ME/EPP não usa indTotTrib — usa pTotTribSN (Focus)
    if body["codigo_opcao_simples_nacional"] == 3:
        body["percentual_total_tributos_simples_nacional"] = float(
            params.get("percentual_total_tributos_simples_nacional") or 6.0
        )
    else:
        body["indicador_total_tributacao"] = str(
            params.get("indicador_total_tributacao") or "0"
        )
    if params.get("inscricao_municipal_prestador"):
        body["inscricao_municipal_prestador"] = str(
            params["inscricao_municipal_prestador"]
        )
    elif params.get("enviar_im_prestador") and provider.municipal_registration:
        # Atibaia/CNC: IM só quando o município exige (senão SEFIN E0120)
        body["inscricao_municipal_prestador"] = provider.municipal_registration
    if params.get("codigo_nbs"):
        body["codigo_nbs"] = str(params["codigo_nbs"])

    body.update(_tomador_flat(customer, fallback_ibge=issue.ibge_code))
    body = _apply_overrides(issue, body)
    return _sanitize_nfsen_sn(body)


def _sanitize_nfsen_sn(body: dict[str, Any]) -> dict[str, Any]:
    """Remove campos proibidos pela SEFIN para ME/EPP Simples Nacional."""
    if int(body.get("codigo_opcao_simples_nacional") or 0) != 3:
        return body
    body.pop("indicador_total_tributacao", None)
    if int(body.get("tipo_retencao_iss") or 0) == 1:
        body.pop("percentual_aliquota_relativa_municipio", None)
    if body.get("percentual_total_tributos_simples_nacional") is None:
        body["percentual_total_tributos_simples_nacional"] = 6.0
    return body


def build_focus_body(issue: NfIssue, *, layout: str) -> dict[str, Any]:
    if layout == "nfsen":
        return to_focus_nfsen(issue)
    return to_focus_nfse(issue)


def _simples_option(tax_regime: str) -> int:
    # Alinhado ao JSON Focus Atibaia: 3 = ME/EPP Simples Nacional
    if tax_regime == TaxRegime.SIMPLES:
        return 3
    return 1


def _tomador_flat(customer: Customer, *, fallback_ibge: str) -> dict[str, Any]:
    out: dict[str, Any] = {"razao_social_tomador": customer.name}
    if customer.document_type == Customer.DocumentType.CPF:
        out["cpf_tomador"] = customer.document
    else:
        out["cnpj_tomador"] = customer.document
    if customer.email:
        out["email_tomador"] = customer.email
    addr = _map_address(customer.address or {}, fallback_ibge=fallback_ibge)
    out["codigo_municipio_tomador"] = addr.get("codigo_municipio") or fallback_ibge
    if addr.get("cep"):
        out["cep_tomador"] = addr["cep"]
    if addr.get("logradouro"):
        out["logradouro_tomador"] = addr["logradouro"]
    if addr.get("numero"):
        out["numero_tomador"] = str(addr["numero"])
    if addr.get("complemento"):
        out["complemento_tomador"] = addr["complemento"]
    if addr.get("bairro"):
        out["bairro_tomador"] = addr["bairro"]
    return out


def _tomador_nested(customer: Customer, *, fallback_ibge: str) -> dict[str, Any]:
    doc_key = "cpf" if customer.document_type == Customer.DocumentType.CPF else "cnpj"
    tomador: dict[str, Any] = {
        doc_key: customer.document,
        "razao_social": customer.name,
    }
    if customer.email:
        tomador["email"] = customer.email
    endereco = _map_address(customer.address or {}, fallback_ibge=fallback_ibge)
    if endereco:
        tomador["endereco"] = endereco
    return tomador


def _map_address(raw: dict, *, fallback_ibge: str) -> dict[str, Any]:
    if not raw:
        return {"codigo_municipio": fallback_ibge}
    aliases = {
        "logradouro": ("logradouro", "street", "rua"),
        "numero": ("numero", "number", "num"),
        "complemento": ("complemento", "complement"),
        "bairro": ("bairro", "district", "neighborhood"),
        "codigo_municipio": ("codigo_municipio", "ibge_code", "city_ibge"),
        "uf": ("uf", "state"),
        "cep": ("cep", "zip", "postal_code"),
    }
    out: dict[str, Any] = {}
    for focus_key, keys in aliases.items():
        for key in keys:
            value = raw.get(key)
            if value not in (None, ""):
                out[focus_key] = str(value).replace("-", "") if focus_key == "cep" else value
                break
    out.setdefault("codigo_municipio", fallback_ibge)
    return out


def _apply_overrides(issue: NfIssue, body: dict[str, Any]) -> dict[str, Any]:
    overrides = {}
    if issue.resolved_rule_id and getattr(issue.resolved_rule, "focus_field_overrides", None):
        overrides = issue.resolved_rule.focus_field_overrides or {}
    if overrides:
        return _deep_merge(body, overrides)
    return body


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
