import pytest
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader

from integrations.receita.exceptions import ReceitaCredentialsMissingError
from integrations.receita.factory import get_receita_gateway
from integrations.receita.http import ReceitaHttpGateway
from integrations.receita.stub import ReceitaStubGateway
from integrations.receita.stub_pdf import render_stub_guia_pdf


def test_factory_default_stub(settings):
    settings.RECEITA_HTTP_MODE = "stub"
    gw = get_receita_gateway()
    assert isinstance(gw, ReceitaStubGateway)
    assert gw.kind == "receita_stub"


def test_factory_http_mode(settings):
    settings.RECEITA_HTTP_MODE = "http"
    settings.SERPRO_CONSUMER_KEY = ""
    settings.SERPRO_CONSUMER_SECRET = ""
    gw = get_receita_gateway()
    assert isinstance(gw, ReceitaHttpGateway)
    with pytest.raises(ReceitaCredentialsMissingError):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")


def _pdf_text(pdf: bytes) -> str:
    return PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""


def test_stub_returns_pdf_bytes():
    result = ReceitaStubGateway().capturar_das(
        cnpj="00000000000191",
        competencia="2024-06",
    )
    assert result.pdf_bytes.startswith(b"%PDF")
    assert len(result.pdf_bytes) > 500
    text = _pdf_text(result.pdf_bytes)
    assert "DAS" in text
    assert "00000000000191" in text


def test_render_stub_guia_pdf_contains_fields():
    pdf = render_stub_guia_pdf(
        tipo="DAS",
        cnpj="61536366000174",
        competencia="2026-08",
        valor_principal=Decimal("150.75"),
        valor_multa=Decimal("0.00"),
        valor_juros=Decimal("0.00"),
        linha_digitavel="2379366000174202608",
        pix_copia_cola="00020126STUBDAS615363660001742026-08",
        data_vencimento="2026-09-09",
    )
    assert pdf.startswith(b"%PDF")
    text = _pdf_text(pdf)
    assert "61536366000174" in text
    assert "2026-08" in text
    assert "150.75" in text
    assert "STUB LAB" in text
