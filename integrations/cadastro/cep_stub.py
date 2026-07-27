from integrations.cadastro.exceptions import CadastroNotFoundError
from integrations.cadastro.cep_port import CepLookupResult


STUB_CEP_OK = "12941410"
STUB_CEP_MISSING = "00000000"


class CepStubGateway:
    kind = "cep_stub"

    def lookup_cep(self, *, cep: str) -> CepLookupResult:
        digits = "".join(ch for ch in cep if ch.isdigit())[:8]
        if digits == STUB_CEP_MISSING or len(digits) != 8:
            raise CadastroNotFoundError("CEP não encontrado.")
        if digits != STUB_CEP_OK and not digits.startswith("12941"):
            # Demais CEPs válidos no stub: endereço genérico Atibaia.
            pass
        return CepLookupResult(
            cep=digits if digits == STUB_CEP_OK else digits,
            logradouro="Rua Almeida Garret" if digits == STUB_CEP_OK else f"Rua Stub {digits[-4:]}",
            bairro="Centro",
            municipio="Atibaia",
            uf="SP",
            codigo_municipio_ibge="3504107",
            raw={"provider": self.kind, "mode": "stub", "cep": digits},
            provider_kind=self.kind,
        )
