from django.conf import settings

from integrations.cadastro.cep_http import CepHttpGateway
from integrations.cadastro.cep_port import CepGateway
from integrations.cadastro.cep_stub import CepStubGateway
from integrations.cadastro.http import CadastroHttpGateway
from integrations.cadastro.port import CadastroGateway
from integrations.cadastro.stub import CadastroStubGateway


def get_cadastro_gateway(*, mode: str | None = None) -> CadastroGateway:
    resolved = (mode or getattr(settings, "CADASTRO_HTTP_MODE", None) or "stub").lower()
    if resolved != "http":
        return CadastroStubGateway()
    return CadastroHttpGateway()


def get_cep_gateway(*, mode: str | None = None) -> CepGateway:
    resolved = (mode or getattr(settings, "CADASTRO_HTTP_MODE", None) or "stub").lower()
    if resolved != "http":
        return CepStubGateway()
    return CepHttpGateway()
