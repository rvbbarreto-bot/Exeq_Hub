from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_date
from uuid import uuid4

from apps.accounts.certificates import assert_certificate_usable
from apps.accounts.proxies import assert_electronic_proxy_usable, das_requires_electronic_proxy
from apps.das.exceptions import DuplicateDasNaturalKeyError
from apps.das.models import GuiaFiscal
from apps.ops.models import StoredFile
from apps.ops.services import enqueue_outbox
from integrations.receita.factory import get_receita_gateway
from shared.storage import get_storage


def _persist_guia_pdf(
    *,
    tenant,
    tipo_guia: str,
    cnpj: str,
    competencia: str,
    pdf_bytes: bytes,
) -> StoredFile | None:
    if not pdf_bytes:
        return None
    object_key = f"das/{tenant.id}/{tipo_guia}/{cnpj}/{competencia}/{uuid4().hex[:12]}.pdf"
    storage = get_storage()
    storage.put(key=object_key, data=pdf_bytes, content_type="application/pdf")
    return StoredFile.objects.create(
        tenant=tenant,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        checksum_sha256=StoredFile.checksum(pdf_bytes),
        encryption="none",
        purpose="das_pdf",
    )


@transaction.atomic
def emitir_guia(
    *,
    tenant,
    idempotency_key: str,
    provider,
    tipo_guia: str,
    competencia: str,
    versao_atual: int = 1,
) -> GuiaFiscal:
    existing = GuiaFiscal.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing

    assert_certificate_usable(
        tenant=tenant,
        cnpj=provider.document,
        purpose="das",
    )
    if das_requires_electronic_proxy():
        assert_electronic_proxy_usable(
            tenant=tenant,
            principal_cnpj=provider.document,
            service_code="PGDASD",
        )

    gateway = get_receita_gateway(tenant=tenant, cnpj=provider.document)
    cnpj = provider.document
    try:
        if tipo_guia == GuiaFiscal.TipoGuia.DAS:
            result = gateway.capturar_das(cnpj=cnpj, competencia=competencia)
        else:
            result = gateway.capturar_darf(cnpj=cnpj, competencia=competencia)
    finally:
        close = getattr(gateway, "close", None)
        if callable(close):
            close()

    stored = _persist_guia_pdf(
        tenant=tenant,
        tipo_guia=tipo_guia,
        cnpj=cnpj,
        competencia=competencia,
        pdf_bytes=result.pdf_bytes,
    )

    try:
        guia = GuiaFiscal.objects.create(
            tenant=tenant,
            provider=provider,
            tipo_guia=tipo_guia,
            competencia=competencia,
            versao_atual=versao_atual,
            idempotency_key=idempotency_key,
            valor_principal=result.valor_principal,
            valor_multa=result.valor_multa,
            valor_juros=result.valor_juros,
            linha_digitavel=result.linha_digitavel,
            pix_copia_cola=result.pix_copia_cola,
            compliance_status=result.compliance_status,
            compliance_motivo=result.compliance_motivo,
            data_vencimento=parse_date(result.data_vencimento)
            if result.data_vencimento
            else None,
            pdf_file=stored,
            pdf_storage_key=stored.object_key if stored else "",
            status=GuiaFiscal.Status.DISPONIVEL,
            metadata=result.raw or {},
        )
    except IntegrityError as exc:
        raise DuplicateDasNaturalKeyError(
            "Já existe guia para prestador/tipo/competência/versão"
        ) from exc

    enqueue_outbox(
        tenant=tenant,
        event_type="guia_fiscal.available",
        aggregate_type="guia_fiscal",
        aggregate_id=guia.id,
        payload={"guia_id": str(guia.id), "tipo_guia": tipo_guia},
    )
    return guia
