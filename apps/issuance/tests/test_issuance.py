from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

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
        codigo_tributacao_nacional_iss="010101",
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
    assert first.focus_ref.startswith("SEFIN-")
    assert first.internal_payload is not None
    assert first.internal_payload.get("provider") == "sefin"
    # sync-first: submitting → authorized (sem polling artificial)
    assert not NfIssueEvent.objects.filter(
        nf_issue=first, to_status=NfIssue.Status.POLLING
    ).exists()
    assert NfIssueEvent.objects.filter(nf_issue=first).count() >= 4
    assert OutboxMessage.objects.filter(
        aggregate_id=first.id,
        event_type="nf_issue.authorized",
    ).exists()
    artifact = NfArtifact.objects.get(nf_issue=first, kind=NfArtifact.Kind.PDF)
    assert artifact.stored_file.purpose == "nf_pdf"
    assert artifact.stored_file.size_bytes > 500
    assert StoredFile.objects.filter(tenant=tenant_a, purpose="nf_pdf").exists()
    xml = NfArtifact.objects.get(nf_issue=first, kind=NfArtifact.Kind.XML)
    assert xml.stored_file.purpose == "nf_xml"


@pytest.mark.django_db
@override_settings(NFSE_DEFAULT_PROVIDER="focus")
def test_lab_focus_authorize_keeps_nfsen_payload(tenant_a, emission_setup):
    """RF-50/EX-FOC-01: Focus permanece operacional com override de lab."""
    first = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-focus-lab",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    first.refresh_from_db()
    assert first.status == NfIssue.Status.AUTHORIZED
    assert first.focus_ref.startswith("NFSEN-")
    assert first.internal_payload.get("cnpj_prestador")



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
def test_cancel_sefin_stub_preserves_xml_and_regenerates_pdf(
    tenant_a, emission_setup, settings, tmp_path
):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-cancel-sefin-stub",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    assert (issue.focus_status_raw or {}).get("xml")
    xml_before = issue.focus_status_raw["xml"]
    cancel_nf_issue(
        issue,
        justificativa="Cancelamento lab EXEQ Hub apos emissao stub",
    )
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED
    assert issue.focus_status_raw.get("xml") == xml_before
    assert issue.focus_status_raw.get("action") == "cancelar"
    pdf = NfArtifact.objects.get(nf_issue=issue, kind=NfArtifact.Kind.PDF)
    assert "danfse-cancelada" in pdf.stored_file.object_key
    from io import BytesIO

    from pypdf import PdfReader
    from shared.storage import get_storage

    data = get_storage().get(key=pdf.stored_file.object_key)
    text = "".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)
    assert "CANCELADA" in text.upper()


@pytest.mark.django_db
def test_cancel_sefin_http_builds_signed_evento(tenant_a, emission_setup, settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.SEFIN_HTTP_MODE = "stub"
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="idem-cancel-sefin-http",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    chave = "35041072237229907000137000000000007026077728989163"
    NfIssue.objects.filter(id=issue.id).update(focus_ref=chave)
    issue.refresh_from_db()

    from integrations.nfse.sefin import SefinNfseProvider
    from integrations.nfse.sefin_client import SefinHttpResponse
    from integrations.nfse.tests.pfx_factory import make_test_pfx

    fake = MagicMock()
    fake.registrar_evento.return_value = SefinHttpResponse(
        status_code=201, data={"ok": True}, xml_bytes=None
    )
    pfx = make_test_pfx(password="segredo")
    provider = SefinNfseProvider(mode="http", client=fake)

    with (
        patch("apps.issuance.services.get_nfse_provider", return_value=provider),
        patch(
            "apps.accounts.certificates.load_primary_pfx_material",
            return_value=(pfx, "segredo"),
        ),
        override_settings(SEFIN_HTTP_MODE="http", SEFIN_ENVIRONMENT="production"),
    ):
        cancel_nf_issue(
            issue,
            justificativa="Cancelamento lab EXEQ Hub via SEFIN HTTP",
        )

    fake.registrar_evento.assert_called_once()
    call_kwargs = fake.registrar_evento.call_args.kwargs
    assert call_kwargs["chave_acesso"] == chave
    evento_xml = call_kwargs["evento_xml"]
    assert b"Signature" in evento_xml
    assert b"e101101" in evento_xml
    assert f"PRE{chave}101101".encode() in evento_xml
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED
    assert issue.focus_status_raw.get("xml")
    assert NfArtifact.objects.filter(
        nf_issue=issue, kind=NfArtifact.Kind.PDF
    ).filter(stored_file__object_key__contains="danfse-cancelada").exists()


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
