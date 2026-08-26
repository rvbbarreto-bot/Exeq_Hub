from django.conf import settings
from django.db import transaction
import logging

from apps.fiscal.exceptions import (
    NationalCatalogError,
    RtcClassificationError,
    TaxRuleNotFoundError,
)
from apps.fiscal.models import FiscalProfile, TaxRuleCatalog
from apps.fiscal.tax_engine import resolve_tax_rule_detailed, rule_to_payload
from apps.fiscal.rtc_emission import build_rtc_emission_context, rtc_mode
from apps.issuance.exceptions import (
    CancelJustificationError,
    FiscalProfileRequiredError,
    FocusCancelFailedError,
    InvalidTransitionError,
)
from apps.issuance.fsm import transition
from apps.issuance.models import FiscalRuleSnapshot, NfIssue
from apps.ops.services import enqueue_outbox
from integrations.nfse.factory import get_nfse_provider, resolve_nfse_route
from integrations.nfse.focus import CANCELLED, FocusHttpError
from integrations.nfse.sefin_client import SefinHttpError
from integrations.nfse.mappers import build_focus_body

logger = logging.getLogger(__name__)


def _extract_rejection_code(raw: dict | None) -> str:
    """EX-FIS-01 — código SEFIN/ADN a partir do raw."""
    data = raw or {}
    erros = data.get("erros") or data.get("errors") or []
    if isinstance(erros, list) and erros:
        first = erros[0]
        if isinstance(first, dict):
            code = first.get("codigo") or first.get("Codigo") or first.get("code")
            if code:
                return str(code)[:64]
        if isinstance(first, str) and first.strip():
            return first.strip()[:64]
    for key in ("codigo", "rejection_code", "cStat"):
        if data.get(key):
            return str(data[key])[:64]
    return "SEFIN_REJECTED"


def _is_transport_recoverable(exc: BaseException) -> bool:
    """EX-NET-02 — timeout/5xx → polling; demais → failed."""
    if isinstance(exc, SefinHttpError) and exc.status_code is not None:
        if exc.status_code >= 500:
            return True
        if exc.status_code in {408, 429}:
            return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "timeout",
            "timed out",
            "temporar",
            "connection",
            "connect",
            "502",
            "503",
            "504",
        )
    )


def _enqueue_process(issue: NfIssue) -> None:
    from apps.issuance.tasks import process_nf_issue

    if settings.NF_SYNC_PROCESSING or settings.CELERY_TASK_ALWAYS_EAGER:
        process_nf_issue(str(issue.tenant_id), str(issue.id))
        return
    transaction.on_commit(
        lambda: process_nf_issue.delay(str(issue.tenant_id), str(issue.id))
    )


def _refresh_forensic_after_emit(issue: NfIssue, *, layout: str) -> None:
    """Pilar 4 — amarra hash do payload enviado ao snapshot forense."""
    from apps.fiscal.rtc_forensic import build_forensic_snapshot, merge_snapshot

    snap = getattr(issue, "rule_snapshot", None)
    if snap is None:
        return
    base = dict(snap.snapshot or {})
    forensic = build_forensic_snapshot(
        iss_payload={k: v for k, v in base.items() if k not in {"forensic", "rtc", "national_catalog"}},
        rtc_block=base.get("rtc"),
        national_catalog=base.get("national_catalog"),
        internal_payload=issue.internal_payload,
        focus_ref=issue.focus_ref or "",
        layout=layout,
    )
    snap.snapshot = merge_snapshot(
        {k: v for k, v in base.items() if k not in {"forensic", "rtc", "national_catalog"}},
        forensic,
    )
    snap.save(update_fields=["snapshot"])
    params = dict(issue.resolved_params or {})
    params["forensic"] = forensic
    params["rtc"] = forensic.get("rtc")
    params["national_catalog"] = forensic.get("national_catalog")
    issue.resolved_params = params
    issue.save(update_fields=["resolved_params", "updated_at"])


def _persist_emission_text(
    issue: NfIssue,
    *,
    descricao_servico: str = "",
    informacoes_complementares: str = "",
) -> None:
    from integrations.nfse.emission_text import normalize_emission_fields

    payload = dict(issue.internal_payload or {})
    emission = normalize_emission_fields(
        descricao_servico=descricao_servico,
        informacoes_complementares=informacoes_complementares,
    )
    if emission:
        payload["emission"] = emission
    else:
        payload.pop("emission", None)
    issue.internal_payload = payload or None
    issue.save(update_fields=["internal_payload", "updated_at"])


def _merge_emission_into_params(issue: NfIssue, payload: dict) -> dict:
    from integrations.nfse.emission_text import normalize_emission_fields

    draft = (issue.internal_payload or {}).get("emission") or {}
    merged = dict(payload)
    for key, value in normalize_emission_fields(
        descricao_servico=draft.get("descricao_servico") or "",
        informacoes_complementares=draft.get("informacoes_complementares") or "",
    ).items():
        merged[key] = value
    return merged


def _apply_nf_issue_fields(
    issue: NfIssue,
    *,
    provider,
    customer,
    service,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    competence_date,
    amount_cents: int,
    descricao_servico: str = "",
    informacoes_complementares: str = "",
) -> NfIssue:
    issue.provider = provider
    issue.customer = customer
    issue.service = service
    issue.fiscal_profile = fiscal_profile
    issue.ibge_code = str(ibge_code)[:7]
    issue.competence_date = competence_date
    issue.amount_cents = amount_cents
    issue.save(
        update_fields=[
            "provider",
            "customer",
            "service",
            "fiscal_profile",
            "ibge_code",
            "competence_date",
            "amount_cents",
            "updated_at",
        ]
    )
    _persist_emission_text(
        issue,
        descricao_servico=descricao_servico,
        informacoes_complementares=informacoes_complementares,
    )
    return issue


@transaction.atomic
def save_nf_draft(
    *,
    tenant,
    idempotency_key: str,
    provider,
    customer,
    service,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    competence_date,
    amount_cents: int,
    draft: NfIssue | None = None,
    descricao_servico: str = "",
    informacoes_complementares: str = "",
) -> NfIssue:
    """
    Persiste NFS-e em status rascunho (sem tributação, fila ou envio).
    Atualiza somente se status=DRAFT; chave de idempotência reutilizada no Hub.
    """
    if fiscal_profile is None:
        raise FiscalProfileRequiredError(
            "Perfil fiscal é obrigatório para salvar a NFS-e."
        )
    if amount_cents < 1:
        raise ValueError("Valor deve ser positivo")

    if draft is not None:
        issue = NfIssue.objects.select_for_update().get(pk=draft.pk, tenant=tenant)
        if issue.status != NfIssue.Status.DRAFT:
            raise InvalidTransitionError(
                "Somente rascunhos podem ser editados no wizard."
            )
        return _apply_nf_issue_fields(
            issue,
            provider=provider,
            customer=customer,
            service=service,
            fiscal_profile=fiscal_profile,
            ibge_code=ibge_code,
            competence_date=competence_date,
            amount_cents=amount_cents,
            descricao_servico=descricao_servico,
            informacoes_complementares=informacoes_complementares,
        )

    existing = (
        NfIssue.objects.select_for_update()
        .filter(tenant=tenant, idempotency_key=idempotency_key)
        .first()
    )
    if existing is not None:
        if existing.status != NfIssue.Status.DRAFT:
            return existing
        return _apply_nf_issue_fields(
            existing,
            provider=provider,
            customer=customer,
            service=service,
            fiscal_profile=fiscal_profile,
            ibge_code=ibge_code,
            competence_date=competence_date,
            amount_cents=amount_cents,
            descricao_servico=descricao_servico,
            informacoes_complementares=informacoes_complementares,
        )

    from apps.accounts.plan_limits import assert_can_create_nf_this_month

    assert_can_create_nf_this_month(tenant)

    issue = NfIssue.objects.create(
        tenant=tenant,
        idempotency_key=idempotency_key,
        status=NfIssue.Status.DRAFT,
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=fiscal_profile,
        ibge_code=str(ibge_code)[:7],
        competence_date=competence_date,
        amount_cents=amount_cents,
    )
    _persist_emission_text(
        issue,
        descricao_servico=descricao_servico,
        informacoes_complementares=informacoes_complementares,
    )
    return issue


@transaction.atomic
def submit_nf_draft(issue: NfIssue, *, actor: str = "api") -> NfIssue:
    """Avança rascunho: tributação → fila → processamento (caminho de create_nf_issue)."""
    # Lock só na NfIssue: select_related em FKs null=True (ex. fiscal_profile)
    # gera OUTER JOIN e o Postgres recusa FOR UPDATE nesse lado.
    NfIssue.objects.select_for_update().get(pk=issue.pk)
    issue = NfIssue.objects.select_related(
        "provider", "customer", "service", "fiscal_profile"
    ).get(pk=issue.pk)

    if issue.status != NfIssue.Status.DRAFT:
        return issue

    if issue.fiscal_profile_id is None:
        raise FiscalProfileRequiredError(
            "Perfil fiscal é obrigatório para emitir a NFS-e."
        )

    fiscal_profile = issue.fiscal_profile
    service = issue.service
    amount_cents = issue.amount_cents
    competence_date = issue.competence_date
    ibge_code = issue.ibge_code
    tenant = issue.tenant

    transition(issue, to_status=NfIssue.Status.PENDING_TAX, actor=actor)

    from apps.master_data.models import ServiceCatalogItem

    if service.operation_kind == ServiceCatalogItem.OperationKind.LOCACAO_BEM:
        issue.rejection_code = "OPERATION_KIND_BLOCKED"
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.REJECTED,
            actor=actor,
            metadata={"code": "OPERATION_KIND_BLOCKED"},
        )
        return issue

    try:
        rule, resolve_meta = resolve_tax_rule_detailed(
            tenant=tenant,
            fiscal_profile=fiscal_profile,
            ibge_code=ibge_code,
            service_code=service.service_code,
            tax_regime=fiscal_profile.tax_regime,
            competence_date=competence_date,
            service=service,
        )
    except TaxRuleNotFoundError:
        issue.rejection_code = "TAX_RULE_NOT_FOUND"
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.REJECTED,
            actor=actor,
            metadata={"code": "TAX_RULE_NOT_FOUND"},
        )
        return issue

    catalog = TaxRuleCatalog.objects.get(id=rule.catalog_id)
    iss_payload = rule_to_payload(rule, resolve_meta=resolve_meta)
    if service.codigo_tributacao_nacional_iss:
        iss_payload["codigo_tributacao_nacional_iss"] = (
            service.codigo_tributacao_nacional_iss
        )
    from apps.fiscal.compliance_hints import service_cnae_compliance_warnings

    compliance = service_cnae_compliance_warnings(provider=issue.provider, service=service)
    if compliance:
        iss_payload["compliance_hints"] = compliance

    route = resolve_nfse_route(
        ibge_code=ibge_code,
        tenant=tenant,
        tax_regime=fiscal_profile.tax_regime,
        competence_date=competence_date,
    )
    layout = getattr(route, "layout", "") or "nfsen"

    try:
        rtc_ctx = build_rtc_emission_context(
            service=service,
            rule=rule,
            amount_cents=amount_cents,
            competence_date=competence_date,
            iss_payload=iss_payload,
            layout=layout,
        )
    except (NationalCatalogError, RtcClassificationError) as exc:
        issue.rejection_code = getattr(exc, "code", "rtc_error") or "rtc_error"
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.REJECTED,
            actor=actor,
            metadata={"code": issue.rejection_code, "detail": str(exc)},
        )
        return issue

    if rtc_mode() == "emit":
        classification = (rtc_ctx["params"].get("rtc") or {}).get("classification") or {}
        if classification.get("status") != "ok":
            issue.rejection_code = "rtc_classification_unresolved"
            issue.save(update_fields=["rejection_code", "updated_at"])
            transition(
                issue,
                to_status=NfIssue.Status.REJECTED,
                actor=actor,
                metadata={"code": issue.rejection_code},
            )
            return issue

    payload = _merge_emission_into_params(issue, rtc_ctx["params"])
    FiscalRuleSnapshot.objects.create(
        tenant=tenant,
        nf_issue=issue,
        source_rule_id=rule.id,
        catalog_version=catalog.version,
        snapshot=payload,
    )
    issue.resolved_rule = rule
    issue.resolved_params = payload
    issue.save(update_fields=["resolved_rule", "resolved_params", "updated_at"])
    transition(issue, to_status=NfIssue.Status.QUEUED, actor=actor)

    enqueue_outbox(
        tenant=tenant,
        event_type="nf_issue.queued",
        aggregate_type="nf_issue",
        aggregate_id=issue.id,
        payload={"nf_issue_id": str(issue.id)},
        correlation_id=issue.correlation_id,
    )
    _enqueue_process(issue)
    issue.refresh_from_db()
    return issue


@transaction.atomic
def create_nf_issue(
    *,
    tenant,
    idempotency_key: str,
    provider,
    customer,
    service,
    fiscal_profile: FiscalProfile,
    ibge_code: str,
    competence_date,
    amount_cents: int,
    descricao_servico: str = "",
    informacoes_complementares: str = "",
) -> NfIssue:
    existing = NfIssue.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing and existing.status != NfIssue.Status.DRAFT:
        return existing

    draft = None
    if existing and existing.status == NfIssue.Status.DRAFT:
        draft = existing

    issue = save_nf_draft(
        tenant=tenant,
        idempotency_key=idempotency_key,
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge_code,
        competence_date=competence_date,
        amount_cents=amount_cents,
        draft=draft,
        descricao_servico=descricao_servico,
        informacoes_complementares=informacoes_complementares,
    )
    return submit_nf_draft(issue, actor="api")


@transaction.atomic
def process_queued_issue(issue: NfIssue) -> NfIssue:
    if issue.status != NfIssue.Status.QUEUED:
        return issue

    transition(issue, to_status=NfIssue.Status.SUBMITTING, actor="worker")
    route = resolve_nfse_route(
        ibge_code=issue.ibge_code,
        tenant_settings=issue.tenant.settings or {},
        tenant=issue.tenant,
        tax_regime=issue.provider.tax_regime,
        competence_date=issue.competence_date,
    )
    provider = get_nfse_provider(
        ibge_code=issue.ibge_code,
        tenant_settings=issue.tenant.settings or {},
        tenant=issue.tenant,
        tax_regime=issue.provider.tax_regime,
        competence_date=issue.competence_date,
        provider_cnpj=getattr(issue.provider, "document", "") or "",
    )

    if route.kind == "sefin":
        from django.conf import settings as dj_settings

        from apps.accounts.certificates import load_primary_pfx_material
        from apps.accounts.exceptions import CertificateNotUsableError
        from integrations.nfse.convenio import (
            MunicipioNaoAderenteError,
            assert_municipio_aderente_nacional,
        )

        sefin_env = getattr(dj_settings, "SEFIN_ENVIRONMENT", None)
        convenio_mode = (
            getattr(dj_settings, "NFSE_CONVENIO_MODE", "stub") or "stub"
        ).lower()
        sefin_http = (
            getattr(dj_settings, "SEFIN_HTTP_MODE", "stub") or "stub"
        ).lower() == "http"
        pfx_bytes: bytes | None = None
        pfx_password = ""
        # ADN convenio HTTP exige mTLS (496 sem cert); carregar A1 antes do gate.
        if convenio_mode == "http" or sefin_http:
            try:
                pfx_bytes, pfx_password = load_primary_pfx_material(
                    tenant=issue.tenant,
                    cnpj=getattr(issue.provider, "document", "") or "",
                    purpose="nfse",
                )
            except CertificateNotUsableError as exc:
                issue.rejection_code = "CERT_NOT_USABLE"
                issue.focus_status_raw = {
                    "provider": "sefin",
                    "action": "preflight",
                    "detail": str(exc),
                    "ex": "EX-PRE-02",
                }
                issue.save(
                    update_fields=["rejection_code", "focus_status_raw", "updated_at"]
                )
                transition(
                    issue,
                    to_status=NfIssue.Status.FAILED,
                    actor="worker",
                    metadata={"code": issue.rejection_code, "ex": "EX-PRE-02"},
                )
                logger.warning(
                    "EX-PRE-02 cert blocked tenant=%s issue=%s detail=%s",
                    issue.tenant_id,
                    issue.id,
                    str(exc)[:200],
                )
                return issue

        try:
            assert_municipio_aderente_nacional(
                issue.ibge_code,
                environment=sefin_env,
                pfx_bytes=pfx_bytes,
                pfx_password=pfx_password,
            )
        except MunicipioNaoAderenteError as exc:
            issue.rejection_code = MunicipioNaoAderenteError.code
            issue.focus_status_raw = {
                "provider": "sefin",
                "action": "preflight",
                "detail": str(exc),
                "sefin_environment": sefin_env,
                "sefin_http_mode": getattr(dj_settings, "SEFIN_HTTP_MODE", None),
                "nfse_convenio_mode": convenio_mode,
            }
            issue.save(
                update_fields=["rejection_code", "focus_status_raw", "updated_at"]
            )
            transition(
                issue,
                to_status=NfIssue.Status.REJECTED,
                actor="worker",
                metadata={"code": issue.rejection_code, "ex": "EX-PRE-01"},
            )
            return issue

    if route.kind == "focus":
        nfse_body = build_focus_body(issue, layout=route.layout)
        emit_payload = {
            "issue_id": str(issue.id),
            "ref": str(issue.id),
            "amount_cents": issue.amount_cents,
            "ibge_code": issue.ibge_code,
            "competence_date": issue.competence_date.isoformat(),
            "resolved_params": issue.resolved_params or {},
            "layout": route.layout,
            "nfse": nfse_body,
        }
    elif route.kind == "sefin":
        from django.conf import settings as dj_settings

        from integrations.nfse.dps import to_sefin_dps_dict, build_dps_xml_from_dict
        from integrations.nfse.xmldsig import sign_dps_xml

        tp_amb = 1 if (getattr(dj_settings, "SEFIN_ENVIRONMENT", "homolog") or "").lower() in {
            "prod",
            "production",
            "producao",
            "produção",
        } else 2
        dps_dict = to_sefin_dps_dict(issue, tp_amb=tp_amb)
        unsigned_xml = build_dps_xml_from_dict(dps_dict)
        nfse_body = {
            "provider": "sefin",
            "layout": route.layout,
            "tp_amb": tp_amb,
            "dps": dps_dict,
            "dps_id": (dps_dict.get("infDPS") or {}).get("Id"),
        }
        emit_payload = {
            "issue_id": str(issue.id),
            "ref": str(issue.id),
            "amount_cents": issue.amount_cents,
            "ibge_code": issue.ibge_code,
            "competence_date": issue.competence_date.isoformat(),
            "resolved_params": issue.resolved_params or {},
            "layout": route.layout,
            "nfse": nfse_body,
        }
        if (getattr(dj_settings, "SEFIN_HTTP_MODE", "stub") or "stub").lower() == "http":
            # A1 já carregado no preflight (pfx_bytes); reutilizar se no mesmo frame.
            if pfx_bytes is None:
                from apps.accounts.certificates import load_primary_pfx_material
                from apps.accounts.exceptions import CertificateNotUsableError

                try:
                    pfx_bytes, pfx_password = load_primary_pfx_material(
                        tenant=issue.tenant,
                        cnpj=getattr(issue.provider, "document", "") or "",
                        purpose="nfse",
                    )
                except CertificateNotUsableError as exc:
                    issue.rejection_code = "CERT_NOT_USABLE"
                    issue.focus_status_raw = {
                        "provider": "sefin",
                        "action": "preflight",
                        "detail": str(exc),
                        "ex": "EX-PRE-02",
                    }
                    issue.save(
                        update_fields=["rejection_code", "focus_status_raw", "updated_at"]
                    )
                    transition(
                        issue,
                        to_status=NfIssue.Status.FAILED,
                        actor="worker",
                        metadata={"code": issue.rejection_code, "ex": "EX-PRE-02"},
                    )
                    logger.warning(
                        "EX-PRE-02 cert blocked tenant=%s issue=%s detail=%s",
                        issue.tenant_id,
                        issue.id,
                        str(exc)[:200],
                    )
                    return issue
            signed_xml = sign_dps_xml(
                dps_xml=unsigned_xml,
                pfx_bytes=pfx_bytes,
                password=pfx_password,
            )
            emit_payload["dps_xml"] = signed_xml
            nfse_body["dps_signed"] = True
    else:
        nfse_body = {
            "provider": route.kind,
            "layout": route.layout,
            "issue_id": str(issue.id),
        }
        emit_payload = {
            "issue_id": str(issue.id),
            "ref": str(issue.id),
            "nfse": nfse_body,
            "layout": route.layout,
        }

    try:
        result = provider.emitir(payload=emit_payload)
    except (SefinHttpError, FocusHttpError) as exc:
        logger.warning(
            "nfse.emit transport_error provider=%s issue=%s detail=%s",
            provider.kind,
            issue.id,
            str(exc)[:200],
        )
        issue.focus_status_raw = {
            "provider": provider.kind,
            "action": "emitir",
            "error": str(exc)[:500],
            "http_status": getattr(exc, "status_code", None),
        }
        issue.save(update_fields=["focus_status_raw", "updated_at"])
        if _is_transport_recoverable(exc):
            transition(issue, to_status=NfIssue.Status.POLLING, actor="worker")
            from apps.issuance.polling import schedule_poll

            schedule_poll(issue)
            return issue
        issue.rejection_code = "SEFIN_TRANSPORT"
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.FAILED,
            actor="worker",
            metadata={"ex": "EX-NET", "detail": str(exc)[:120]},
        )
        return issue

    issue.internal_payload = nfse_body
    issue.focus_ref = result.external_ref
    issue.focus_status_raw = result.raw
    issue.save(
        update_fields=[
            "internal_payload",
            "focus_ref",
            "focus_status_raw",
            "updated_at",
        ]
    )
    status = (result.status or "").lower()
    logger.info(
        "nfse.emit outcome=%s provider=%s issue=%s ref=%s",
        status or "unknown",
        provider.kind,
        issue.id,
        issue.focus_ref,
    )
    if route.kind == "focus":
        _refresh_forensic_after_emit(issue, layout=route.layout)

    if status == "authorized":
        # Caminho feliz síncrono: submitting → authorized (sem polling artificial).
        transition(
            issue,
            to_status=NfIssue.Status.AUTHORIZED,
            actor="provider",
            metadata={"focus_ref": issue.focus_ref, "provider": provider.kind},
        )
        enqueue_outbox(
            tenant=issue.tenant,
            event_type="nf_issue.authorized",
            aggregate_type="nf_issue",
            aggregate_id=issue.id,
            payload={"nf_issue_id": str(issue.id), "focus_ref": issue.focus_ref},
            correlation_id=issue.correlation_id,
        )
        from apps.issuance.artifacts import ensure_authorized_artifacts

        ensure_authorized_artifacts(issue)
    elif status == "rejected":
        issue.rejection_code = _extract_rejection_code(result.raw)
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.REJECTED,
            actor="provider",
            metadata={
                "provider": provider.kind,
                "raw_status": status,
                "rejection_code": issue.rejection_code,
                "ex": "EX-FIS-01",
            },
        )
    else:
        transition(issue, to_status=NfIssue.Status.POLLING, actor="worker")
        from apps.issuance.polling import schedule_poll

        schedule_poll(issue)
    return issue


@transaction.atomic
def cancel_nf_issue(
    issue: NfIssue,
    *,
    justificativa: str,
    codigo_cancelamento: int | None = None,
    actor: str = "api",
) -> NfIssue:
    text = (justificativa or "").strip()
    if not (15 <= len(text) <= 255):
        raise CancelJustificationError(
            "justificativa deve ter entre 15 e 255 caracteres"
        )
    if issue.status != NfIssue.Status.AUTHORIZED:
        raise InvalidTransitionError(
            f"Só é possível cancelar nota Autorizada. Status atual: {issue.get_status_display()} ({issue.status})"
        )
    if not issue.focus_ref:
        raise FocusCancelFailedError(
            "referência do Provedor Exeq ausente — não é possível cancelar no provedor"
        )

    provider = get_nfse_provider(
        ibge_code=issue.ibge_code,
        tenant_settings=issue.tenant.settings or {},
        tenant=issue.tenant,
        tax_regime=issue.provider.tax_regime,
        competence_date=issue.competence_date,
        provider_cnpj=getattr(issue.provider, "document", "") or "",
    )
    cancel_kwargs: dict = {
        "ref": issue.focus_ref,
        "justificativa": text,
        "codigo_cancelamento": codigo_cancelamento,
    }
    if getattr(provider, "kind", "") == "sefin":
        from django.conf import settings as dj_settings

        from apps.accounts.certificates import load_primary_pfx_material
        from integrations.nfse.evento import build_cancel_evento_from_issue
        from integrations.nfse.xmldsig import sign_ped_reg_evento_xml

        if (getattr(dj_settings, "SEFIN_HTTP_MODE", "stub") or "stub").lower() == "http":
            tp_amb = 1 if (getattr(dj_settings, "SEFIN_ENVIRONMENT", "homolog") or "").lower() in {
                "prod",
                "production",
                "producao",
                "produção",
            } else 2
            unsigned = build_cancel_evento_from_issue(
                issue,
                justificativa=text,
                codigo_cancelamento=codigo_cancelamento,
                tp_amb=tp_amb,
            )
            pfx_bytes, pfx_password = load_primary_pfx_material(
                tenant=issue.tenant,
                cnpj=getattr(issue.provider, "document", "") or "",
                purpose="nfse",
            )
            cancel_kwargs["evento_xml"] = sign_ped_reg_evento_xml(
                evento_xml=unsigned,
                pfx_bytes=pfx_bytes,
                password=pfx_password,
            )
    try:
        result = provider.cancelar(**cancel_kwargs)
    except FocusHttpError as exc:
        raise FocusCancelFailedError(str(exc)) from exc
    except SefinHttpError as exc:
        raise FocusCancelFailedError(str(exc)) from exc

    # Preserva XML/DANFSe da autorização — cancel HTTP/stub não devolve NFSe.
    prev_raw = dict(issue.focus_status_raw or {})
    merged_raw = {**prev_raw, **(result.raw or {})}
    for key in ("xml", "nfse_xml", "xml_nfse", "url_danfse", "caminho_xml_nota_fiscal"):
        if not merged_raw.get(key) and prev_raw.get(key):
            merged_raw[key] = prev_raw[key]
    issue.focus_status_raw = merged_raw
    issue.save(update_fields=["focus_status_raw", "updated_at"])

    status = (result.status or "").lower()
    raw_status = str((result.raw or {}).get("status") or "").lower()
    if (
        status not in CANCELLED
        and status != "cancelled"
        and raw_status not in CANCELLED
    ):
        # Cancelamento assíncrono: mantém authorized e deixa QA/poll confirmar
        if raw_status in {"processando_cancelamento", "cancelamento_solicitado"} or status in {
            "processando_cancelamento",
            "cancelamento_solicitado",
            "processing",
        }:
            raise FocusCancelFailedError(
                "Provedor Exeq aceitou o pedido, mas o cancelamento ainda está em processamento. "
                "Use a ação «Consultar status no provedor» em alguns segundos."
            )
        raise FocusCancelFailedError(
            f"Cancelamento não confirmado pelo provedor: {status or raw_status or 'unknown'}"
        )

    transition(
        issue,
        to_status=NfIssue.Status.CANCELLED,
        actor=actor or "api",
        metadata={
            "focus_ref": issue.focus_ref,
            "justificativa": text[:80],
            "codigo_cancelamento": codigo_cancelamento,
            "provider": provider.kind,
        },
    )
    enqueue_outbox(
        tenant=issue.tenant,
        event_type="nf_issue.cancelled",
        aggregate_type="nf_issue",
        aggregate_id=issue.id,
        payload={"nf_issue_id": str(issue.id), "focus_ref": issue.focus_ref},
        correlation_id=issue.correlation_id,
    )
    from apps.issuance.artifacts import ensure_cancelled_artifacts

    ensure_cancelled_artifacts(issue)
    return issue


@transaction.atomic
def reprocess_nf_issue(issue: NfIssue) -> NfIssue:
    transition(issue, to_status=NfIssue.Status.PENDING_TAX, actor="api")
    issue.rejection_code = ""
    issue.save(update_fields=["rejection_code", "updated_at"])
    # Re-enter create path tax resolution by rebuilding from current fields
    profile = issue.fiscal_profile
    try:
        rule, resolve_meta = resolve_tax_rule_detailed(
            tenant=issue.tenant,
            fiscal_profile=profile,
            ibge_code=issue.ibge_code,
            service_code=issue.service.service_code,
            tax_regime=profile.tax_regime,
            competence_date=issue.competence_date,
            service=issue.service,
        )
    except TaxRuleNotFoundError:
        issue.rejection_code = "TAX_RULE_NOT_FOUND"
        issue.save(update_fields=["rejection_code", "updated_at"])
        transition(
            issue,
            to_status=NfIssue.Status.REJECTED,
            actor="api",
            metadata={"code": "TAX_RULE_NOT_FOUND"},
        )
        return issue

    catalog = TaxRuleCatalog.objects.get(id=rule.catalog_id)
    payload = rule_to_payload(rule, resolve_meta=resolve_meta)
    if issue.service.codigo_tributacao_nacional_iss:
        payload["codigo_tributacao_nacional_iss"] = (
            issue.service.codigo_tributacao_nacional_iss
        )
    FiscalRuleSnapshot.objects.update_or_create(
        nf_issue=issue,
        defaults={
            "tenant": issue.tenant,
            "source_rule_id": rule.id,
            "catalog_version": catalog.version,
            "snapshot": payload,
        },
    )
    issue.resolved_rule = rule
    issue.resolved_params = payload
    issue.save(update_fields=["resolved_rule", "resolved_params", "updated_at"])
    transition(issue, to_status=NfIssue.Status.QUEUED, actor="api")
    enqueue_outbox(
        tenant=issue.tenant,
        event_type="nf_issue.queued",
        aggregate_type="nf_issue",
        aggregate_id=issue.id,
        payload={"nf_issue_id": str(issue.id)},
        correlation_id=issue.correlation_id,
    )
    _enqueue_process(issue)
    issue.refresh_from_db()
    return issue
