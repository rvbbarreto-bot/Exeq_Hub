"""Testes sync portal SEFIN (sem HTTP)."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.portal_sync import (
    collect_issue_ids_for_portal_sync,
    is_sefin_chave,
    refresh_nf_issue_from_portal,
    should_sync_issue,
)
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from integrations.nfse.tests.test_evento import CHAVE as SEFIN_CHAVE_50


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


def test_is_sefin_chave():
    assert is_sefin_chave(SEFIN_CHAVE_50)
    assert not is_sefin_chave("SEFIN-ABC")


@pytest.mark.django_db
def test_should_sync_throttles_recent_portal_sync(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="sync-throttle",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 28),
        amount_cents=3111,
    )
    chave = SEFIN_CHAVE_50
    NfIssue.objects.filter(pk=issue.pk).update(
        focus_ref=chave,
        focus_status_raw={"portal_sync_at": timezone.now().isoformat()},
    )
    issue.refresh_from_db()
    assert should_sync_issue(issue) is False
    assert should_sync_issue(issue, force=True) is True


@pytest.mark.django_db
def test_refresh_nf_issue_from_portal_applies_cancelled(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="sync-cancel",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 28),
        amount_cents=3111,
    )
    chave = SEFIN_CHAVE_50
    NfIssue.objects.filter(pk=issue.pk).update(focus_ref=chave)
    issue.refresh_from_db()

    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    from integrations.nfse.port import NfseEmitResult

    mock_provider.consultar.return_value = NfseEmitResult(
        external_ref=chave,
        status="cancelled",
        raw={"provider": "sefin", "status": "cancelled", "cStat": "101"},
    )
    with patch("apps.issuance.polling.get_nfse_provider", return_value=mock_provider):
        refresh_nf_issue_from_portal(issue)
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED
    assert issue.focus_status_raw.get("portal_sync_at")


@pytest.mark.django_db
def test_collect_issue_ids_respects_limit(tenant_a, emission_setup, settings):
    settings.NFSE_PORTAL_SYNC_LIST_LIMIT = 2
    issues = []
    for i in range(3):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key=f"sync-collect-{i}",
            provider=emission_setup["provider"],
            customer=emission_setup["customer"],
            service=emission_setup["service"],
            fiscal_profile=emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2026, 8, 28),
            amount_cents=1000 + i,
        )
        chave = SEFIN_CHAVE_50[: -1] + str(i)
        NfIssue.objects.filter(pk=issue.pk).update(focus_ref=chave)
        issue.refresh_from_db()
        issues.append(issue)
    ids = collect_issue_ids_for_portal_sync(issues)
    assert len(ids) == 2
