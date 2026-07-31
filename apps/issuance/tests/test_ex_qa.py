"""Testes EX-* críticos do LLR §5 (aceite M4 QA)."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.artifacts import ensure_authorized_artifacts
from apps.issuance.models import NfArtifact, NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from integrations.nfse.port import NfseEmitResult
from integrations.nfse.sefin_client import SefinHttpError


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
@override_settings(NFSE_CONVENIO_DENY_IBGE="3504107", NF_SYNC_PROCESSING=True)
def test_ex_pre_01_municipio_nao_aderente_blocks_without_http(tenant_a, emission_setup):
    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    with patch("apps.issuance.services.get_nfse_provider", return_value=mock_provider):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key="ex-pre-01",
            provider=emission_setup["provider"],
            customer=emission_setup["customer"],
            service=emission_setup["service"],
            fiscal_profile=emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2024, 6, 15),
            amount_cents=1000,
        )
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.REJECTED
    assert issue.rejection_code == "MUNICIPIO_NAO_ADERENTE"
    mock_provider.emitir.assert_not_called()


@pytest.mark.django_db
@override_settings(SEFIN_HTTP_MODE="http", NF_SYNC_PROCESSING=True)
def test_ex_pre_02_cert_ausente_fails_without_emit(tenant_a, emission_setup):
    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    with (
        patch("apps.issuance.services.get_nfse_provider", return_value=mock_provider),
        patch(
            "apps.accounts.certificates.load_primary_pfx_material",
            side_effect=__import__(
                "apps.accounts.exceptions", fromlist=["CertificateNotUsableError"]
            ).CertificateNotUsableError("Certificado digital A1 primary ausente para o CNPJ"),
        ),
    ):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key="ex-pre-02",
            provider=emission_setup["provider"],
            customer=emission_setup["customer"],
            service=emission_setup["service"],
            fiscal_profile=emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2024, 6, 15),
            amount_cents=1000,
        )
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.FAILED
    assert issue.rejection_code == "CERT_NOT_USABLE"
    mock_provider.emitir.assert_not_called()


@pytest.mark.django_db
@override_settings(NF_SYNC_PROCESSING=True)
def test_ex_net_02_timeout_goes_to_polling(tenant_a, emission_setup):
    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    mock_provider.emitir.side_effect = SefinHttpError("HTTP timeout talking to SEFIN")
    with (
        patch("apps.issuance.services.get_nfse_provider", return_value=mock_provider),
        patch("apps.issuance.polling.schedule_poll") as schedule_poll,
    ):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key="ex-net-02",
            provider=emission_setup["provider"],
            customer=emission_setup["customer"],
            service=emission_setup["service"],
            fiscal_profile=emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2024, 6, 15),
            amount_cents=1000,
        )
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.POLLING
    schedule_poll.assert_called()


@pytest.mark.django_db
@override_settings(NF_SYNC_PROCESSING=True)
def test_ex_fis_01_sefin_reject_persists_code(tenant_a, emission_setup):
    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    mock_provider.emitir.return_value = NfseEmitResult(
        external_ref="CHAVE",
        status="rejected",
        raw={
            "provider": "sefin",
            "erros": [{"codigo": "E0207", "mensagem": "DPS invalida"}],
        },
    )
    with patch("apps.issuance.services.get_nfse_provider", return_value=mock_provider):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key="ex-fis-01",
            provider=emission_setup["provider"],
            customer=emission_setup["customer"],
            service=emission_setup["service"],
            fiscal_profile=emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2024, 6, 15),
            amount_cents=1000,
        )
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.REJECTED
    assert issue.rejection_code == "E0207"


@pytest.mark.django_db
def test_ex_pdf_01_pdf_failure_keeps_authorized_xml(tenant_a, emission_setup, settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.NF_SYNC_PROCESSING = True
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="ex-pdf-01",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=1000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED
    NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.PDF).delete()
    with patch(
        "integrations.nfse.danfse.render_danfse_pdf",
        side_effect=RuntimeError("pdf boom"),
    ):
        ensure_authorized_artifacts(issue)
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED
    assert (issue.focus_status_raw or {}).get("pdf_pending") is True
    assert NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.XML).exists()
    assert not NfArtifact.objects.filter(nf_issue=issue, kind=NfArtifact.Kind.PDF).exists()
