from django.conf import settings

from apps.accounts.certificates import load_primary_pfx_material
from apps.accounts.secrets import get_tenant_secret_plaintext
from integrations.receita.http import ReceitaHttpGateway
from integrations.receita.port import ReceitaGateway
from integrations.receita.stub import ReceitaStubGateway


def _serpro_credential(*, tenant, key_name: str) -> str:
    if tenant is not None:
        value = get_tenant_secret_plaintext(
            tenant=tenant,
            provider="serpro",
            key_name=key_name,
        )
        if value:
            return value
    env_map = {
        "consumer_key": "SERPRO_CONSUMER_KEY",
        "consumer_secret": "SERPRO_CONSUMER_SECRET",
    }
    setting = env_map.get(key_name, "")
    return (getattr(settings, setting, None) or "") if setting else ""


def get_receita_gateway(
    *,
    mode: str | None = None,
    tenant=None,
    cnpj: str | None = None,
) -> ReceitaGateway:
    resolved = (mode or getattr(settings, "RECEITA_HTTP_MODE", None) or "stub").lower()
    if resolved != "http":
        return ReceitaStubGateway()

    digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    pfx_bytes = b""
    pfx_password = ""
    if tenant is not None and digits:
        pfx_bytes, pfx_password = load_primary_pfx_material(tenant=tenant, cnpj=digits)

    return ReceitaHttpGateway(
        consumer_key=_serpro_credential(tenant=tenant, key_name="consumer_key"),
        consumer_secret=_serpro_credential(tenant=tenant, key_name="consumer_secret"),
        pfx_bytes=pfx_bytes,
        pfx_password=pfx_password,
        contratante_cnpj=digits,
    )
