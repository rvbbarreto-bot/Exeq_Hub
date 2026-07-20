from django.conf import settings
from django.db import transaction

from apps.fiscal.exceptions import TaxRuleNotFoundError
from apps.fiscal.models import FiscalProfile, TaxRuleCatalog
from apps.fiscal.tax_engine import resolve_tax_rule, rule_to_payload
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
from integrations.nfse.mappers import build_focus_body


def _enqueue_process(issue: NfIssue) -> None:
    from apps.issuance.tasks import process_nf_issue

    if settings.NF_SYNC_PROCESSING or settings.CELERY_TASK_ALWAYS_EAGER:
        process_nf_issue(str(issue.tenant_id), str(issue.id))
        return
    transaction.on_commit(
        lambda: process_nf_issue.delay(str(issue.tenant_id), str(issue.id))
    )


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
) -> NfIssue:
    existing = NfIssue.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing

    if fiscal_profile is None:
        raise FiscalProfileRequiredError(
            "Perfil fiscal é obrigatório para emitir a NFS-e."
        )

    issue = NfIssue.objects.create(
        tenant=tenant,
        idempotency_key=idempotency_key,
        status=NfIssue.Status.DRAFT,
        provider=provider,
        customer=customer,
        service=service,
        fiscal_profile=fiscal_profile,
        ibge_code=ibge_code,
        competence_date=competence_date,
        amount_cents=amount_cents,
    )
    transition(issue, to_status=NfIssue.Status.PENDING_TAX, actor="api")

    try:
        rule = resolve_tax_rule(
            tenant=tenant,
            fiscal_profile=fiscal_profile,
            ibge_code=ibge_code,
            service_code=service.service_code,
            tax_regime=fiscal_profile.tax_regime,
            competence_date=competence_date,
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
    payload = rule_to_payload(rule)
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
    transition(issue, to_status=NfIssue.Status.QUEUED, actor="api")

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
    )
    nfse_body = build_focus_body(issue, layout=route.layout)
    result = provider.emitir(
        payload={
            "issue_id": str(issue.id),
            "ref": str(issue.id),
            "amount_cents": issue.amount_cents,
            "ibge_code": issue.ibge_code,
            "competence_date": issue.competence_date.isoformat(),
            "resolved_params": issue.resolved_params or {},
            "layout": route.layout,
            "nfse": nfse_body,
        }
    )
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
    transition(issue, to_status=NfIssue.Status.POLLING, actor="worker")
    if result.status == "authorized":
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
    else:
        from apps.issuance.polling import schedule_poll

        schedule_poll(issue)
    return issue


@transaction.atomic
def cancel_nf_issue(
    issue: NfIssue,
    *,
    justificativa: str,
    codigo_cancelamento: int | None = None,
) -> NfIssue:
    text = (justificativa or "").strip()
    if not (15 <= len(text) <= 255):
        raise CancelJustificationError(
            "justificativa deve ter entre 15 e 255 caracteres"
        )
    if issue.status != NfIssue.Status.AUTHORIZED:
        raise InvalidTransitionError(
            f"Transição inválida: {issue.status} -> {NfIssue.Status.CANCELLED}"
        )
    if not issue.focus_ref:
        raise FocusCancelFailedError("focus_ref ausente — não é possível cancelar no provedor")

    provider = get_nfse_provider(
        ibge_code=issue.ibge_code,
        tenant_settings=issue.tenant.settings or {},
        tenant=issue.tenant,
        tax_regime=issue.provider.tax_regime,
        competence_date=issue.competence_date,
    )
    try:
        result = provider.cancelar(
            ref=issue.focus_ref,
            justificativa=text,
            codigo_cancelamento=codigo_cancelamento,
        )
    except FocusHttpError as exc:
        raise FocusCancelFailedError(str(exc)) from exc

    issue.focus_status_raw = result.raw
    issue.save(update_fields=["focus_status_raw", "updated_at"])

    status = (result.status or "").lower()
    if status not in CANCELLED and status != "cancelled":
        raise FocusCancelFailedError(
            f"Cancelamento não confirmado pelo provedor: {status or 'unknown'}"
        )

    transition(
        issue,
        to_status=NfIssue.Status.CANCELLED,
        actor="api",
        metadata={
            "focus_ref": issue.focus_ref,
            "justificativa": text[:80],
            "codigo_cancelamento": codigo_cancelamento,
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
    return issue


@transaction.atomic
def reprocess_nf_issue(issue: NfIssue) -> NfIssue:
    transition(issue, to_status=NfIssue.Status.PENDING_TAX, actor="api")
    issue.rejection_code = ""
    issue.save(update_fields=["rejection_code", "updated_at"])
    # Re-enter create path tax resolution by rebuilding from current fields
    profile = issue.fiscal_profile
    try:
        rule = resolve_tax_rule(
            tenant=issue.tenant,
            fiscal_profile=profile,
            ibge_code=issue.ibge_code,
            service_code=issue.service.service_code,
            tax_regime=profile.tax_regime,
            competence_date=issue.competence_date,
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
    payload = rule_to_payload(rule)
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
