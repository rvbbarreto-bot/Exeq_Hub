from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.exceptions import InvalidTransitionError
from apps.issuance.fsm import transition
from apps.issuance.models import NfArtifact, NfIssue, NfIssueEvent
from apps.issuance.services import cancel_nf_issue, create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from apps.ops.models import OutboxMessage, StoredFile
from integrations.nfse.port import NfseEmitResult


@pytest.fixture
def emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Serviço",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN",
        tax_regime=TaxRegime.SIMPLES,
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)
    return {
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_idempotent_create_and_authorize(tenant_a, emission_setup):
    kwargs = dict(
        tenant=tenant_a,
        idempotency_key="idem-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    first = create_nf_issue(**kwargs)
    second = create_nf_issue(**kwargs)
    assert first.id == second.id
    first.refresh_from_db()
    assert first.status == NfIssue.Status.AUTHORIZED
    assert first.focus_ref.startswith("NFSEN-")
    assert first.internal_payload is not None
    assert first.internal_payload.get("cnpj_prestador")
    assert NfIssueEvent.objects.filter(nf_issue=first).count() >= 5
    assert OutboxMessage.objects.filter(
        aggregate_id=first.id,
        event_type="nf_issue.authorized",
    ).exists()
    artifact = NfArtifact.objects.get(nf_issue=first, kind=NfArtifact.Kind.PDF)
    assert artifact.stored_file.purpose == "nf_pdf"
    assert StoredFile.objects.filter(tenant=tenant_a, purpose="nf_pdf").exists()
    xml = NfArtifact.objects.get(nf_issue=first, kind=NfArtifact.Kind.XML)
    assert xml.stored_file.purpose == "nf_xml"


@pytest.mark.django_db
def test_create_requires_fiscal_profile(tenant_a, emission_setup):
    from apps.issuance.exceptions import FiscalProfileRequiredError

    with pytest.raises(FiscalProfileRequiredError):
        create_nf_issue(
            tenant=tenant_a,
            idempotency_key="no-profile",
            provider=emission_setup["provider"],
            customer=emission_setup["customer"],
            service=emission_setup["service"],
            fiscal_profile=None,
            ibge_code="3504107",
            competence_date=date(2024, 6, 15),
            amount_cents=1000,
        )
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-2",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3550308",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    assert issue.status == NfIssue.Status.REJECTED
    assert issue.rejection_code == "TAX_RULE_NOT_FOUND"
    assert NfIssueEvent.objects.filter(
        nf_issue=issue,
        to_status=NfIssue.Status.REJECTED,
    ).exists()


@pytest.mark.django_db
def test_invalid_transition_blocked(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-3",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    NfIssue.objects.filter(id=issue.id).update(status=NfIssue.Status.DRAFT)
    issue.refresh_from_db()
    with pytest.raises(InvalidTransitionError):
        transition(issue, to_status=NfIssue.Status.AUTHORIZED, actor="api")


@pytest.mark.django_db
def test_cancel_authorized_calls_provider(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-cancel-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED
    mock_provider = MagicMock()
    mock_provider.kind = "focus"
    mock_provider.cancelar.return_value = NfseEmitResult(
        external_ref=issue.focus_ref,
        status="cancelled",
        raw={"status": "cancelado", "provider": "focus"},
    )
    with patch(
        "apps.issuance.services.get_nfse_provider",
        return_value=mock_provider,
    ):
        cancel_nf_issue(
            issue,
            justificativa="Servico cancelado por acordo entre as partes",
        )
    mock_provider.cancelar.assert_called_once()
    kwargs = mock_provider.cancelar.call_args.kwargs
    assert kwargs["ref"] == issue.focus_ref
    assert "acordo entre as partes" in kwargs["justificativa"]
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED
    assert OutboxMessage.objects.filter(
        aggregate_id=issue.id,
        event_type="nf_issue.cancelled",
    ).exists()


@pytest.mark.django_db
def test_cancel_not_authorized_blocked(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-cancel-2",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    NfIssue.objects.filter(id=issue.id).update(status=NfIssue.Status.POLLING)
    issue.refresh_from_db()
    with pytest.raises(InvalidTransitionError, match="Autorizada"):
        cancel_nf_issue(
            issue,
            justificativa="Servico cancelado por acordo entre as partes",
        )


@pytest.mark.django_db
def test_nf_issue_api(api_client, auth_header, tenant_a, emission_setup):
    response = api_client.post(
        "/api/v1/nf-issue/",
        {
            "idempotency_key": "api-1",
            "provider_id": str(emission_setup["provider"].id),
            "customer_id": str(emission_setup["customer"].id),
            "service_id": str(emission_setup["service"].id),
            "fiscal_profile_id": str(emission_setup["profile"].id),
            "ibge_code": "3504107",
            "competence_date": "2024-06-15",
            "amount_cents": 2500,
        },
        format="json",
        **auth_header,
    )
    assert response.status_code == 201
    assert response.data["status"] == "authorized"

    cancel = api_client.post(
        f"/api/v1/nf-issue/{response.data['id']}/cancel/",
        {"justificativa": "Servico cancelado por acordo entre as partes"},
        format="json",
        **auth_header,
    )
    assert cancel.status_code == 200
    assert cancel.data["status"] == "cancelled"
