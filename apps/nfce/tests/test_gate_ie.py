"""Gate NFC-e — IE emitente em produção HTTP."""

from __future__ import annotations

import pytest

from apps.master_data.models import Provider, TaxRegime
from apps.nfce.gate import build_gate_payload


@pytest.fixture
def nfce_http_prod(settings):
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "http"
    settings.NFCE_DEFAULT_TP_AMB = "1"
    return settings


@pytest.fixture
def nfce_provider(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="61536366000174",
        legal_name="Emitente NFC-e gate",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="",
        address={
            "logradouro": "Rua Teste",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_municipio_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_gate_blocks_isento_ie_in_production(nfce_http_prod, tenant_a, nfce_provider):
    nfce_provider.state_registration = "ISENTO"
    nfce_provider.save(update_fields=["state_registration"])
    payload = build_gate_payload(
        tenant=tenant_a,
        provider_id=str(nfce_provider.id),
        tp_amb="1",
    )
    ie_chk = next(c for c in payload["checks"] if c["id"] == "ie")
    assert ie_chk["ok"] is False
    assert payload["can_create"] is False


@pytest.mark.django_db
def test_gate_passes_numeric_ie_in_production(nfce_http_prod, tenant_a, nfce_provider):
    nfce_provider.state_registration = "123456789112"
    nfce_provider.save(update_fields=["state_registration"])
    payload = build_gate_payload(
        tenant=tenant_a,
        provider_id=str(nfce_provider.id),
        tp_amb="1",
    )
    ie_chk = next(c for c in payload["checks"] if c["id"] == "ie")
    assert ie_chk["ok"] is True
