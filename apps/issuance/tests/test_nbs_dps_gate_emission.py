"""Emissão com NBS cadastrado e portão cNBS fechado (evita E1235 em produção)."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from integrations.nfse.dps import build_dps_xml_from_dict, to_sefin_dps_dict
from integrations.nfse.port import NfseEmitResult


@pytest.fixture
def nbs_emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador NBS Gate",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente Gate",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="17.19",
        description="Publicidade e propaganda",
        codigo_tributacao_nacional_iss="171900",
        lc116_item="17.19",
        codigo_nbs="113022100",
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
        service_code="17.19",
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


def _authorized_stub(*, payload):
    return NfseEmitResult(
        external_ref="35041072237229907000137000000000049926077728989163",
        status="authorized",
        raw={"provider": "sefin", "stub": True},
    )


@pytest.mark.django_db
@override_settings(
    NFSE_DPS_CNBS_MODE="off",
    SEFIN_ENVIRONMENT="production",
    NF_SYNC_PROCESSING=True,
)
def test_emission_below_seven_reais_omits_cnbs_when_gate_closed(
    tenant_a, nbs_emission_setup
):
    captured: dict = {}
    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    mock_provider.emitir.side_effect = lambda *, payload: (
        captured.update({"payload": payload}) or _authorized_stub(payload=payload)
    )

    with patch("apps.issuance.services.get_nfse_provider", return_value=mock_provider):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key="nbs-gate-off-499",
            provider=nbs_emission_setup["provider"],
            customer=nbs_emission_setup["customer"],
            service=nbs_emission_setup["service"],
            fiscal_profile=nbs_emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2026, 2, 1),
            amount_cents=499,
            codigo_nbs="113022100",
        )

    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED
    assert issue.amount_cents == 499
    assert issue.resolved_params.get("codigo_nbs") == "113022100"

    dps = captured["payload"]["nfse"]["dps"]
    c_serv = dps["infDPS"]["serv"]["cServ"]
    assert "cNBS" not in c_serv
    xml = build_dps_xml_from_dict(dps)
    assert b"cNBS" not in xml


@pytest.mark.django_db
@override_settings(
    NFSE_DPS_CNBS_MODE="on",
    SEFIN_ENVIRONMENT="production",
    NF_SYNC_PROCESSING=True,
)
def test_emission_below_seven_reais_includes_cnbs_when_gate_open(
    tenant_a, nbs_emission_setup
):
    captured: dict = {}
    mock_provider = MagicMock()
    mock_provider.kind = "sefin"
    mock_provider.emitir.side_effect = lambda *, payload: (
        captured.update({"payload": payload}) or _authorized_stub(payload=payload)
    )

    with patch("apps.issuance.services.get_nfse_provider", return_value=mock_provider):
        issue = create_nf_issue(
            tenant=tenant_a,
            idempotency_key="nbs-gate-on-699",
            provider=nbs_emission_setup["provider"],
            customer=nbs_emission_setup["customer"],
            service=nbs_emission_setup["service"],
            fiscal_profile=nbs_emission_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2026, 2, 1),
            amount_cents=699,
            codigo_nbs="113022100",
        )

    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED
    dps = captured["payload"]["nfse"]["dps"]
    assert dps["infDPS"]["serv"]["cServ"]["cNBS"] == "113022100"

    rebuilt = to_sefin_dps_dict(issue, tp_amb=1)
    assert rebuilt["infDPS"]["serv"]["cServ"]["cNBS"] == "113022100"
