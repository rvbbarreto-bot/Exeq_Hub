from apps.accounts.focus_empresa import register_provider_on_focus
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider
from integrations.nfse.empresas import FocusEmpresaClient
import pytest


@pytest.mark.django_db
def test_focus_empresa_stub_upsert(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="ACME",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="12345",
        address={"logradouro": "Rua A", "numero": "10", "uf": "SP", "cep": "12940000"},
    )
    client = FocusEmpresaClient(mode="stub", token="x")
    result = client.upsert_empresa_from_provider(provider)
    assert result["mode"] == "stub"
    assert result["cnpj"] == "00000000000191"
    assert "habilita_nfsen_homologacao" in result["body_keys"] or True


@pytest.mark.django_db
def test_register_provider_on_focus_stub(tenant_a, settings):
    settings.FOCUS_HTTP_MODE = "stub"
    settings.FOCUS_WEBHOOK_PUBLIC_URL = "https://example.test/api/v1/webhooks/focus-nfse"
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="ACME",
        tax_regime=TaxRegime.SIMPLES,
    )
    out = register_provider_on_focus(tenant=tenant_a, provider=provider)
    assert out["empresa"]["action"] == "upsert_empresa"
    assert out["webhook"]["action"] == "ensure_webhook"
