from datetime import date, timedelta
from decimal import Decimal

from integrations.receita.port import GuiaCapturaResult
from integrations.receita.stub_pdf import STUB_DAS_PDF


class ReceitaStubGateway:
    """Stub local até homologação SERPRO Integra Contador (Sprint 6b)."""

    kind = "receita_stub"

    def capturar_das(self, *, cnpj: str, competencia: str) -> GuiaCapturaResult:
        return self._build(cnpj=cnpj, competencia=competencia, tipo="DAS")

    def capturar_darf(self, *, cnpj: str, competencia: str) -> GuiaCapturaResult:
        return self._build(cnpj=cnpj, competencia=competencia, tipo="DARF")

    def _build(self, *, cnpj: str, competencia: str, tipo: str) -> GuiaCapturaResult:
        year, month = competencia.split("-")
        due = date(int(year), int(month), 20) + timedelta(days=20)
        principal = Decimal("150.75") if tipo == "DAS" else Decimal("80.00")
        return GuiaCapturaResult(
            valor_principal=principal,
            valor_multa=Decimal("0.00"),
            valor_juros=Decimal("0.00"),
            linha_digitavel=f"23793{cnpj[-8:]}{competencia.replace('-', '')}",
            pix_copia_cola=f"00020126STUB{tipo}{cnpj}{competencia}",
            compliance_status="aprovado",
            compliance_motivo="stub_ok",
            data_vencimento=due.isoformat(),
            pdf_bytes=STUB_DAS_PDF,
            raw={"provider": self.kind, "tipo": tipo, "mode": "stub"},
        )
