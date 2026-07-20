from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.focus_webhook import (
    InvalidFocusWebhookAuthError,
    ingest_focus_nfse_webhook,
)
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from django.test import override_settings


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
        lc116_item="1.01",
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
@override_settings(FOCUS_WEBHOOK_SECRET="secret-focus")
def test_focus_webhook_authorizes_polling_issue(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="wh-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    # create_nf_issue already authorizes in stub; reset to polling for webhook path
    NfIssue.objects.filter(id=issue.id).update(status=NfIssue.Status.POLLING)
    issue.refresh_from_db()
    issue.focus_ref = "NFSEN-WEBHOOK01"
    issue.save(update_fields=["focus_ref", "updated_at"])

    inbox = ingest_focus_nfse_webhook(
        raw_authorization="secret-focus",
        payload={"ref": "NFSEN-WEBHOOK01", "status": "autorizado"},
    )
    assert inbox.status == "processed"
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED

    again = ingest_focus_nfse_webhook(
        raw_authorization="secret-focus",
        payload={"ref": "NFSEN-WEBHOOK01", "status": "autorizado"},
    )
    assert again.id == inbox.id


@pytest.mark.django_db
@override_settings(FOCUS_WEBHOOK_SECRET="secret-focus")
def test_focus_webhook_cancels_authorized_issue(tenant_a, emission_setup):
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="wh-cancel-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=10000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED
    issue.focus_ref = "NFSEN-CANCEL01"
    issue.save(update_fields=["focus_ref", "updated_at"])

    inbox = ingest_focus_nfse_webhook(
        raw_authorization="secret-focus",
        payload={"ref": "NFSEN-CANCEL01", "status": "cancelado"},
    )
    assert inbox.status == "processed"
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED


@pytest.mark.django_db
@override_settings(FOCUS_WEBHOOK_SECRET="secret-focus")
def test_focus_webhook_rejects_bad_secret(tenant_a, emission_setup):
    with pytest.raises(InvalidFocusWebhookAuthError):
        ingest_focus_nfse_webhook(
            raw_authorization="wrong",
            payload={"ref": "x", "status": "autorizado"},
        )
