"""Convênio municipal ADN com mTLS opcional (RF-01 / cobertura municípios aderentes).

ADN `parametros_municipais/.../convenio` exige certificado de cliente (HTTP 496
sem mTLS). Em `NFSE_CONVENIO_MODE=http` o Hub usa o A1 do prestador (ou PFX ops).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from shared.exceptions import DomainError

ATIBAIA_IBGE = "3504107"


class MunicipioNaoAderenteError(DomainError):
    code = "MUNICIPIO_NAO_ADERENTE"


@dataclass(frozen=True)
class ConvenioStatus:
    ibge_code: str
    aderente: bool
    environment: str
    source: str  # stub_cache | http_cache | deny | http_error
    raw: dict | None = None


def normalize_sefin_environment(value: str | None) -> str:
    env = (value or getattr(settings, "SEFIN_ENVIRONMENT", None) or "homolog").lower()
    if env in {"prod", "production", "producao", "produção"}:
        return "production"
    return "homolog"


def _csv_codes(raw: str | None) -> frozenset[str]:
    return frozenset(c.strip() for c in (raw or "").split(",") if c.strip())


def _deny_ibges() -> frozenset[str]:
    return _csv_codes(getattr(settings, "NFSE_CONVENIO_DENY_IBGE", None))


def _seed_for_environment(environment: str) -> frozenset[str]:
    """Semente de cache por ambiente (lab). Produção ≠ homolog (estudo PO R1/R3)."""
    if environment == "production":
        raw = getattr(settings, "NFSE_NATIONAL_IBGE_CODES", None) or ATIBAIA_IBGE
        return _csv_codes(raw)
    raw = getattr(settings, "NFSE_CONVENIO_HOMOLOG_IBGE_CODES", None)
    if raw is None:
        return frozenset()
    return _csv_codes(raw)


def _cache_key(ibge: str, environment: str) -> str:
    return f"nfse:convenio:{environment}:{ibge}"


def _interpret_convenio_payload(status_code: int, data: dict) -> bool:
    """Heurística de aptidão a partir do JSON ADN (campos variam por versão)."""
    if status_code != 200 or not data:
        return False
    if data.get("erros") or data.get("errors"):
        return False
    for key in ("apto", "aderente", "conveniado", "habilitado", "ativo"):
        if key in data:
            return bool(data[key])
    situacao = str(data.get("situacao") or data.get("status") or "").lower()
    if situacao:
        if situacao in {"inapto", "inativo", "nao_aderente", "não_aderente", "bloqueado"}:
            return False
        if situacao in {"apto", "ativo", "aderente", "conveniado", "habilitado", "ok"}:
            return True
    # 200 + JSON sem erros → tratar como apto (manual municípios conveniados).
    return True


def get_convenio_status(
    ibge_code: str,
    *,
    environment: str | None = None,
    force_refresh: bool = False,
    pfx_bytes: bytes | None = None,
    pfx_password: str = "",
) -> ConvenioStatus:
    """Consulta aptidão com cache (RF-01). Stub lab; HTTP+mTLS via ADN quando configurado."""
    ibge = "".join(ch for ch in (ibge_code or "") if ch.isdigit())
    env = normalize_sefin_environment(environment)

    if ibge in _deny_ibges():
        return ConvenioStatus(
            ibge_code=ibge,
            aderente=False,
            environment=env,
            source="deny",
        )

    key = _cache_key(ibge, env)
    if not force_refresh and pfx_bytes is None:
        cached = cache.get(key)
        if isinstance(cached, dict) and "aderente" in cached:
            return ConvenioStatus(
                ibge_code=ibge,
                aderente=bool(cached["aderente"]),
                environment=env,
                source=str(cached.get("source") or "cache"),
                raw=cached.get("raw"),
            )

    mode = (getattr(settings, "NFSE_CONVENIO_MODE", None) or "stub").lower()
    if mode == "http":
        status = _fetch_convenio_http(
            ibge,
            environment=env,
            pfx_bytes=pfx_bytes,
            pfx_password=pfx_password,
        )
    else:
        seed = _seed_for_environment(env)
        status = ConvenioStatus(
            ibge_code=ibge,
            aderente=ibge in seed,
            environment=env,
            source="stub_cache",
            raw={"seed": sorted(seed), "environment": env},
        )

    ttl = int(getattr(settings, "NFSE_CONVENIO_CACHE_SECONDS", 21600) or 21600)
    cache.set(
        key,
        {
            "aderente": status.aderente,
            "source": status.source,
            "raw": status.raw,
            "environment": env,
        },
        timeout=ttl,
    )
    return status


def _adn_param_base(environment: str) -> str:
    override = (getattr(settings, "ADN_PARAM_BASE_URL", None) or "").strip()
    if override:
        return override.rstrip("/")
    if environment == "production":
        return "https://adn.nfse.gov.br"
    return "https://adn.producaorestrita.nfse.gov.br"


def _fetch_convenio_http(
    ibge: str,
    *,
    environment: str,
    pfx_bytes: bytes | None = None,
    pfx_password: str = "",
) -> ConvenioStatus:
    """GET ADN parametros_municipais/{codMun}/convenio (mTLS quando A1 disponível)."""
    import httpx

    from integrations.nfse.sefin_mtls import SefinMtlsError, build_sefin_mtls_context

    base = _adn_param_base(environment)
    paths = (
        f"/parametros_municipais/{ibge}/convenio",
        f"/parametrizacao/{ibge}/convenio",
    )
    verify: bool | object = True
    mtls = None
    if pfx_bytes:
        try:
            mtls = build_sefin_mtls_context(pfx_bytes=pfx_bytes, password=pfx_password)
            verify = mtls.ssl_context
        except SefinMtlsError as exc:
            return ConvenioStatus(
                ibge_code=ibge,
                aderente=False,
                environment=environment,
                source="http_error",
                raw={"error": f"mtls_pfx: {exc}"[:200]},
            )

    last_error = ""
    try:
        for path in paths:
            url = f"{base}{path}"
            try:
                with httpx.Client(timeout=20.0, verify=verify) as client:
                    resp = client.get(url)
                if resp.status_code == 496:
                    last_error = "496 SSL Certificate Required (informe A1 / mTLS)"
                    continue
                ctype = resp.headers.get("content-type", "")
                data = resp.json() if "json" in ctype else {}
                if not isinstance(data, dict):
                    data = {"body": data}
                if resp.status_code == 404:
                    last_error = f"404 {path}"
                    continue
                aderente = _interpret_convenio_payload(resp.status_code, data)
                return ConvenioStatus(
                    ibge_code=ibge,
                    aderente=aderente,
                    environment=environment,
                    source="http_cache",
                    raw={
                        "http_status": resp.status_code,
                        "url": url,
                        "mtls": bool(pfx_bytes),
                        **data,
                    },
                )
            except Exception as exc:  # noqa: BLE001 — EX-PRE-01: falha ≠ adesão
                last_error = str(exc)[:200]
                continue
        return ConvenioStatus(
            ibge_code=ibge,
            aderente=False,
            environment=environment,
            source="http_error",
            raw={"error": last_error or "convenio_http_failed", "mtls": bool(pfx_bytes)},
        )
    finally:
        if mtls is not None:
            mtls.close()


def assert_municipio_aderente_nacional(
    ibge_code: str,
    *,
    environment: str | None = None,
    pfx_bytes: bytes | None = None,
    pfx_password: str = "",
) -> ConvenioStatus:
    status = get_convenio_status(
        ibge_code,
        environment=environment,
        pfx_bytes=pfx_bytes,
        pfx_password=pfx_password,
        force_refresh=bool(pfx_bytes),
    )
    if not status.aderente:
        raise MunicipioNaoAderenteError(
            f"Município IBGE {status.ibge_code} não apto ao Ambiente Nacional "
            f"NFS-e no ambiente {status.environment} (EX-PRE-01)"
        )
    return status


def check_convenio_batch(
    ibge_codes: list[str],
    *,
    environment: str | None = None,
    pfx_bytes: bytes | None = None,
    pfx_password: str = "",
    force_refresh: bool = True,
) -> list[ConvenioStatus]:
    """Consulta vários IBGE (smoke multi-município / RF-01)."""
    out: list[ConvenioStatus] = []
    for raw in ibge_codes:
        ibge = "".join(ch for ch in (raw or "") if ch.isdigit())
        if not ibge:
            continue
        out.append(
            get_convenio_status(
                ibge,
                environment=environment,
                pfx_bytes=pfx_bytes,
                pfx_password=pfx_password,
                force_refresh=force_refresh,
            )
        )
    return out
