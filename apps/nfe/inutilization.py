"""Inutilização de faixa de numeração NF-e (U15 / D-14)."""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import transaction

from apps.nfe.exceptions import NfeValidationError
from apps.nfe.gate import default_tp_amb, upsert_number_series
from apps.nfe.models import NfeInutilization, NfeInvoice, NfeNumberSeries
from apps.nfe.services import nfe_feature_enabled, require_nfe_enabled
from integrations.sefaz_nfe import get_nfe_provider


def _year_aa(ano: str | int | None) -> str:
    if ano is None or ano == "":
        return str(date.today().year)[-2:]
    digits = "".join(c for c in str(ano) if c.isdigit())
    if len(digits) >= 4:
        return digits[-2:]
    return digits.zfill(2)[-2:]


def inutilize_number_range(
    *,
    tenant,
    provider,
    series: int = 1,
    tp_amb: str | None = None,
    n_ini: int,
    n_fin: int,
    x_just: str,
    ano: str | int | None = None,
    uf: str | None = None,
    actor: str = "api",
) -> NfeInutilization:
    """
    Inutiliza nIni–nFin junto à SEFAZ (stub/HTTP) e avança next_number se aceito.

    Regra contador: se next_number <= n_fin, next_number = n_fin + 1.
    Auditoria rejeitada/falha persiste mesmo com raise (commit antes do raise).
    """
    require_nfe_enabled()
    if provider.tenant_id != tenant.id:
        raise NfeValidationError("provider de outro tenant")

    just = (x_just or "").strip()
    if not (15 <= len(just) <= 255):
        raise NfeValidationError("justificativa deve ter 15–255 caracteres")
    try:
        ini = int(n_ini)
        fin = int(n_fin)
    except (TypeError, ValueError) as exc:
        raise NfeValidationError("n_ini/n_fin inválidos") from exc
    if ini < 1 or fin < 1 or fin < ini:
        raise NfeValidationError("faixa n_ini/n_fin inválida")
    if fin - ini + 1 > 10_000:
        raise NfeValidationError("faixa máxima 10000 números")

    ser = max(1, int(series or 1))
    amb = (tp_amb or default_tp_amb())[:1]
    aa = _year_aa(ano)

    conflict = NfeInvoice.objects.filter(
        tenant=tenant,
        provider=provider,
        series=ser,
        tp_amb=amb,
        number__gte=ini,
        number__lte=fin,
        status__in={
            NfeInvoice.Status.AUTHORIZED,
            NfeInvoice.Status.CANCELLED,
            NfeInvoice.Status.CANCEL_REQUESTED,
            NfeInvoice.Status.POLLING,
        },
    ).exists()
    if conflict:
        raise NfeValidationError(
            "faixa conflita com NF-e já numerada/autorizada (ou em processamento)"
        )

    emit_uf = (uf or getattr(settings, "NFE_PIVOT_UF", "SP") or "SP").upper()
    addr = provider.address if isinstance(provider.address, dict) else {}
    if addr.get("uf"):
        emit_uf = str(addr["uf"]).upper()

    cnpj = "".join(ch for ch in str(provider.document or "") if ch.isdigit())

    sefaz = get_nfe_provider()
    from apps.nfe.attempts import AttemptTimer, record_transmission_attempt

    with AttemptTimer() as timer:
        result = sefaz.inutilizar(
            n_ini=ini,
            n_fin=fin,
            x_just=just,
            context={
                "tenant": tenant,
                "cnpj": cnpj,
                "tp_amb": amb,
                "uf": emit_uf,
                "series": ser,
                "ano": aa,
            },
        )
    record_transmission_attempt(
        tenant=tenant,
        invoice=None,
        stage="inut",
        result=result,
        provider_kind=getattr(sefaz, "kind", ""),
        duration_ms=timer.ms,
    )
    raw = result.raw if isinstance(result.raw, dict) else {}
    status = (
        NfeInutilization.Status.ACCEPTED
        if result.status == "accepted"
        else (
            NfeInutilization.Status.REJECTED
            if result.status == "rejected"
            else NfeInutilization.Status.FAILED
        )
    )

    with transaction.atomic():
        row = NfeInutilization.objects.create(
            tenant=tenant,
            provider=provider,
            series=ser,
            tp_amb=amb,
            ano=aa,
            n_ini=ini,
            n_fin=fin,
            x_just=just[:255],
            status=status,
            protocol=result.protocol or "",
            provider_raw=raw,
            actor=(actor or "api")[:120],
        )
        if status == NfeInutilization.Status.ACCEPTED:
            series_row = (
                NfeNumberSeries.objects.select_for_update()
                .filter(
                    tenant=tenant,
                    provider=provider,
                    series=ser,
                    tp_amb=amb,
                    is_active=True,
                )
                .first()
            )
            if series_row is None:
                upsert_number_series(
                    tenant=tenant,
                    provider=provider,
                    series=ser,
                    tp_amb=amb,
                    next_number=fin + 1,
                    is_active=True,
                )
            elif series_row.next_number <= fin:
                series_row.next_number = fin + 1
                series_row.save(update_fields=["next_number", "updated_at"])

    if status != NfeInutilization.Status.ACCEPTED:
        msg = result.rejection_message or "inutilização não aceita"
        code = result.rejection_code or ""
        raise NfeValidationError(f"{msg}" + (f" (cStat={code})" if code else ""))

    return row
