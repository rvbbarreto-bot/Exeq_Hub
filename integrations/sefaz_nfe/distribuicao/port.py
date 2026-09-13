"""Porta e adapters NFeDistribuicaoDFe (stub / HTTP AN)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings

from integrations.sefaz_nfe.distribuicao.stub_xml import build_stub_res_nfe_xml

CSTAT_NENHUM_DOCUMENTO = "137"
CSTAT_DOCUMENTOS_LOCALIZADOS = "138"
CSTAT_CONSUMO_INDEVIDO = "656"


def _pad_nsu(value: str | int) -> str:
    digits = "".join(c for c in str(value or "0") if c.isdigit())
    return digits.zfill(15)[-15:]


def _next_nsu(ult_nsu: str, step: int = 1) -> str:
    current = int("".join(c for c in ult_nsu if c.isdigit()) or "0")
    return _pad_nsu(current + step)


def _stub_access_key(*, cnpj: str, nsu_num: int) -> str:
    cnpj_d = "".join(c for c in cnpj if c.isdigit())[:14].zfill(14)
    prefix = f"352601{cnpj_d}55001"
    suffix = str(nsu_num).zfill(44 - len(prefix))
    return (prefix + suffix)[:44]


@dataclass(frozen=True)
class NfeDistribuicaoDocument:
    nsu: str
    schema_type: str
    xml_bytes: bytes


@dataclass(frozen=True)
class NfeDistribuicaoResult:
    c_stat: str
    x_motivo: str
    ult_nsu: str
    max_nsu: str
    dh_resp: str = ""
    documents: tuple[NfeDistribuicaoDocument, ...] = ()
    raw: dict[str, Any] | None = None


class NfeDistribuicaoProvider(Protocol):
    kind: str

    def consultar_dist_nsu(
        self,
        *,
        cnpj: str,
        ult_nsu: str,
        tp_amb: str = "2",
        context: dict[str, Any] | None = None,
    ) -> NfeDistribuicaoResult: ...


class StubNfeDistribuicaoProvider:
    """Provider lab — simula distNSU sem SOAP."""

    kind = "stub"

    def consultar_dist_nsu(
        self,
        *,
        cnpj: str,
        ult_nsu: str,
        tp_amb: str = "2",
        context: dict[str, Any] | None = None,
    ) -> NfeDistribuicaoResult:
        ctx = context or {}
        mode = str(ctx.get("stub_mode") or settings.NFE_ENTRADA_STUB_MODE or "137")
        ult = _pad_nsu(ult_nsu)

        if mode == "656":
            return NfeDistribuicaoResult(
                c_stat=CSTAT_CONSUMO_INDEVIDO,
                x_motivo="Rejeicao: Consumo Indevido",
                ult_nsu=ult,
                max_nsu=ult,
                dh_resp="2026-01-15T10:00:00-03:00",
                raw={"stub_mode": mode},
            )

        if mode == "137":
            return NfeDistribuicaoResult(
                c_stat=CSTAT_NENHUM_DOCUMENTO,
                x_motivo="Nenhum documento localizado",
                ult_nsu=ult,
                max_nsu=ult,
                dh_resp="2026-01-15T10:00:00-03:00",
                raw={"stub_mode": "137"},
            )

        # mode "138" — retorna resNFe NSU 1 e 2, depois 137
        start = int(ult) + 1
        if start > 2:
            return NfeDistribuicaoResult(
                c_stat=CSTAT_NENHUM_DOCUMENTO,
                x_motivo="Nenhum documento localizado",
                ult_nsu=ult,
                max_nsu=ult,
                dh_resp="2026-01-15T10:00:00-03:00",
                raw={"stub_mode": "138_exhausted"},
            )

        docs: list[NfeDistribuicaoDocument] = []
        for offset in range(2):
            nsu_num = start + offset
            if nsu_num > 2:
                break
            nsu = _pad_nsu(nsu_num)
            access_key = _stub_access_key(cnpj=cnpj, nsu_num=nsu_num)
            docs.append(
                NfeDistribuicaoDocument(
                    nsu=nsu,
                    schema_type="resNFe",
                    xml_bytes=build_stub_res_nfe_xml(
                        access_key=access_key,
                        recipient_cnpj=cnpj,
                        number=nsu_num,
                    ),
                )
            )

        max_nsu = docs[-1].nsu if docs else ult
        return NfeDistribuicaoResult(
            c_stat=CSTAT_DOCUMENTOS_LOCALIZADOS,
            x_motivo="Documento(s) localizado(s)",
            ult_nsu=ult,
            max_nsu=max_nsu,
            dh_resp="2026-01-15T10:00:00-03:00",
            documents=tuple(docs),
            raw={"stub_mode": "138", "count": len(docs)},
        )


class HttpNfeDistribuicaoProvider:
    """HTTP real — NFeDistribuicaoDFe Ambiente Nacional."""

    kind = "http"

    def consultar_dist_nsu(
        self,
        *,
        cnpj: str,
        ult_nsu: str,
        tp_amb: str = "2",
        context: dict[str, Any] | None = None,
    ) -> NfeDistribuicaoResult:
        from apps.accounts.certificates import load_primary_pfx_material
        from apps.nfe.entrada.exceptions import DistributionError
        from integrations.sefaz_nfe.access_key import UF_IBGE_CODE
        from integrations.sefaz_nfe.distribuicao.endpoints import resolve_distribuicao_endpoints
        from integrations.sefaz_nfe.distribuicao.parse import (
            RetDistParseError,
            decode_doc_zip,
            parse_ret_dist_dfe_response,
        )
        from integrations.sefaz_nfe.distribuicao.transport import post_nfe_distribuicao

        ctx = context or {}
        tenant = ctx.get("tenant")
        provider = ctx.get("provider")
        if tenant is None:
            raise DistributionError("context.tenant é obrigatório para HttpNfeDistribuicaoProvider")

        cnpj_d = "".join(c for c in cnpj if c.isdigit())[:14]
        cuf_autor = str(ctx.get("cuf_autor") or "")
        if not cuf_autor and provider is not None:
            uf = str((provider.address or {}).get("uf") or "SP").upper()
            cuf_autor = UF_IBGE_CODE.get(uf, "35")
        cuf_autor = cuf_autor or "35"

        if getattr(settings, "NFE_ENTRADA_HTTP_DRY_RUN", False):
            return NfeDistribuicaoResult(
                c_stat=CSTAT_NENHUM_DOCUMENTO,
                x_motivo="Dry-run — consulta não enviada",
                ult_nsu=_pad_nsu(ult_nsu),
                max_nsu=_pad_nsu(ult_nsu),
                raw={"dry_run": True},
            )

        pfx_bytes, password = load_primary_pfx_material(
            tenant=tenant,
            cnpj=cnpj_d,
            purpose="nfe",
        )
        endpoints = resolve_distribuicao_endpoints(tp_amb=tp_amb)
        timeout = float(getattr(settings, "NFE_ENTRADA_DIST_TIMEOUT", 60) or 60)
        session = ctx.get("http_session")

        http_resp = post_nfe_distribuicao(
            url=endpoints.distribuicao,
            tp_amb=tp_amb,
            cnpj=cnpj_d,
            ult_nsu=ult_nsu,
            cuf_autor=cuf_autor,
            pfx_bytes=pfx_bytes,
            password=password,
            timeout=timeout,
            session=session,
        )

        if http_resp.http_status >= 400:
            raise DistributionError(f"SEFAZ AN HTTP {http_resp.http_status}")

        try:
            parsed = parse_ret_dist_dfe_response(http_resp.body)
        except RetDistParseError as exc:
            raise DistributionError(str(exc)) from exc

        documents: list[NfeDistribuicaoDocument] = []
        for item in parsed.documents:
            xml_bytes = decode_doc_zip(
                nsu=item.nsu,
                schema_hint=item.schema_type,
                payload=item.payload,
            )
            schema_type = item.schema_type
            if schema_type == "resNFe" and b"procNFe" in xml_bytes[:200]:
                schema_type = "procNFe"
            documents.append(
                NfeDistribuicaoDocument(
                    nsu=item.nsu,
                    schema_type=schema_type,
                    xml_bytes=xml_bytes,
                )
            )

        return NfeDistribuicaoResult(
            c_stat=parsed.c_stat,
            x_motivo=parsed.x_motivo,
            ult_nsu=parsed.ult_nsu,
            max_nsu=parsed.max_nsu,
            dh_resp=parsed.dh_resp,
            documents=tuple(documents),
            raw={
                "http_status": http_resp.http_status,
                "authority": endpoints.authority,
                "doc_count": len(documents),
            },
        )


def get_nfe_distribuicao_provider() -> NfeDistribuicaoProvider:
    mode = (getattr(settings, "NFE_ENTRADA_HTTP_MODE", "stub") or "stub").lower()
    if mode == "http":
        return HttpNfeDistribuicaoProvider()
    return StubNfeDistribuicaoProvider()
