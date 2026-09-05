"""Política nacional default (demais UFs — onda 1)."""

from __future__ import annotations

from apps.fiscal.document_policy.types import DocumentModel, DocumentRoute, SaleContext
from shared.validators import validate_cnpj, validate_cpf

# R$ 10.000,00
ANONYMOUS_LIMIT_CENTS = 1_000_000
# R$ 200.000,00 — acima exige NF-e mesmo identificado
IDENTIFIED_NFCE_MAX_CENTS = 20_000_000


def _norm_doc(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def evaluate_sale(ctx: SaleContext) -> DocumentRoute:
    cpf_raw = _norm_doc(ctx.cpf)
    cnpj_raw = _norm_doc(ctx.cnpj)
    has_cpf = bool(cpf_raw)
    has_cnpj = bool(cnpj_raw)

    if has_cpf and has_cnpj:
        return DocumentRoute(
            model=DocumentModel.BLOCKED,
            errors=(
                {
                    "field": "identification",
                    "message": "informe apenas CPF ou CNPJ, não ambos",
                },
            ),
            reasons=("ambiguous_identification",),
        )

    if has_cnpj:
        try:
            validate_cnpj(cnpj_raw)
        except ValueError:
            return DocumentRoute(
                model=DocumentModel.BLOCKED,
                errors=({"field": "cnpj", "message": "CNPJ inválido"},),
                reasons=("invalid_cnpj",),
            )
        return DocumentRoute(
            model=DocumentModel.NFE,
            omit_dest=False,
            reasons=("exeq_cnpj_routes_nfe",),
        )

    if has_cpf:
        try:
            validate_cpf(cpf_raw)
        except ValueError:
            return DocumentRoute(
                model=DocumentModel.BLOCKED,
                errors=({"field": "cpf", "message": "CPF inválido"},),
                reasons=("invalid_cpf",),
            )
        if ctx.total_cents >= IDENTIFIED_NFCE_MAX_CENTS:
            return DocumentRoute(
                model=DocumentModel.BLOCKED,
                errors=(
                    {
                        "field": "total_cents",
                        "message": "valor exige NF-e modelo 55, não NFC-e",
                    },
                ),
                reasons=("identified_high_value_requires_nfe",),
            )
        return DocumentRoute(
            model=DocumentModel.NFCE,
            omit_dest=False,
            reasons=("cpf_identified_nfce",),
        )

    if ctx.delivery:
        return DocumentRoute(
            model=DocumentModel.BLOCKED,
            errors=(
                {
                    "field": "identification",
                    "message": "entrega exige CPF ou CNPJ do consumidor",
                },
            ),
            reasons=("delivery_requires_identification",),
        )

    if ctx.installment:
        return DocumentRoute(
            model=DocumentModel.BLOCKED,
            errors=(
                {
                    "field": "identification",
                    "message": "venda a prazo exige CPF ou CNPJ",
                },
            ),
            reasons=("installment_requires_identification",),
        )

    if ctx.total_cents >= ANONYMOUS_LIMIT_CENTS:
        return DocumentRoute(
            model=DocumentModel.BLOCKED,
            errors=(
                {
                    "field": "identification",
                    "message": "valor exige identificação do consumidor (CPF ou CNPJ)",
                },
            ),
            reasons=("anonymous_limit_exceeded",),
        )

    return DocumentRoute(
        model=DocumentModel.NFCE,
        omit_dest=True,
        reasons=("anonymous_nfce",),
    )


class DefaultDocumentPolicy:
    uf = "DEFAULT"

    def evaluate(self, ctx: SaleContext) -> DocumentRoute:
        return evaluate_sale(ctx)
