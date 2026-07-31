from __future__ import annotations

from datetime import date

from integrations.cadastro.exceptions import (
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)
from integrations.cadastro.port import CadastralAddress, CadastralLookupResult


# CNPJs de fixture — únicos que o stub atende (não inventar dados de CNPJ real).
STUB_CNPJ_OK = "00000000000191"
STUB_CNPJ_MISSING = "00000000000272"


class CadastroStubGateway:
    """Stub local para testes — só fixtures conhecidas. CNPJ real exige modo http."""

    kind = "cadastro_stub"

    def lookup_cnpj(self, *, cnpj: str) -> CadastralLookupResult:
        digits = "".join(ch for ch in cnpj if ch.isdigit())
        if digits == STUB_CNPJ_MISSING:
            raise CadastroNotFoundError("CNPJ não encontrado na base cadastral.")
        if digits != STUB_CNPJ_OK:
            raise CadastroProviderUnavailableError(
                "Consulta em modo stub: use o CNPJ de teste 00.000.000/0001-91 "
                "ou defina CADASTRO_HTTP_MODE=http para consultar a Receita (BrasilAPI)."
            )

        legal = "ACME SERVICOS CONTABEIS LTDA"
        raw = {
            "provider": self.kind,
            "mode": "stub",
            "cnpj": digits,
            "razao_social": legal,
            "nome_fantasia": "ACME Contábil",
            "descricao_situacao_cadastral": "ATIVA",
            "data_inicio_atividade": "2015-03-12",
            "natureza_juridica": "206-2 - Sociedade Empresária Limitada",
            "cnae_fiscal": 6920601,
            "cnae_fiscal_descricao": "Atividades de contabilidade",
            "cnaes_secundarios": [
                {
                    "codigo": 7020400,
                    "descricao": "Atividades de consultoria em gestão empresarial",
                }
            ],
            "descricao_porte": "EMPRESA DE PEQUENO PORTE",
            "opcao_pelo_simples": True,
            "opcao_pelo_mei": False,
            "ddd_telefone_1": "11 99999-0000",
            "email": "",
            "logradouro": "Rua Almeida Garret",
            "numero": "100",
            "complemento": "Sala 1",
            "bairro": "Centro",
            "cep": "12941410",
            "municipio": "Atibaia",
            "uf": "SP",
            "codigo_municipio_ibge": "3504107",
        }
        return CadastralLookupResult(
            document=digits,
            legal_name=legal,
            trade_name=str(raw["nome_fantasia"]),
            situacao_cadastral=str(raw["descricao_situacao_cadastral"]),
            data_abertura=date(2015, 3, 12),
            natureza_juridica=str(raw["natureza_juridica"]),
            cnae_principal="6920601 - Atividades de contabilidade",
            cnaes_secundarios=[
                "7020400 - Atividades de consultoria em gestão empresarial"
            ],
            porte=str(raw["descricao_porte"]),
            optante_simples=True,
            optante_mei=False,
            telefone=str(raw["ddd_telefone_1"]),
            email="",
            address=CadastralAddress(
                logradouro="Rua Almeida Garret",
                numero="100",
                complemento="Sala 1",
                bairro="Centro",
                cep="12941410",
                municipio="Atibaia",
                uf="SP",
                codigo_municipio_ibge="3504107",
            ),
            raw=raw,
            provider_kind=self.kind,
        )
