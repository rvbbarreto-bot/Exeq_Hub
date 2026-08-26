from datetime import timedelta
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-change-me-sprint0-exeq-hub-32b")
DEBUG = env("DJANGO_DEBUG", "true").lower() == "true"
# SEC-P1-01: piloto/prod via DJANGO_ALLOWED_HOSTS (csv). Lab mantém localhost.
_allowed = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver") or ""
ALLOWED_HOSTS: list[str] = [h.strip() for h in _allowed.split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts",
    "apps.master_data",
    "apps.fiscal",
    "apps.ops",
    "apps.issuance",
    "apps.nfe",
    "apps.billing",
    "apps.das",
    "apps.channel",
    "apps.scheduling",
    "apps.food",
    "apps.hub_v4",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "shared.middleware.AdminIpAllowlistMiddleware",
    "shared.middleware.TenantRLSMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.hub_v4.nav_flags.hub_nav_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if env("EXEQ_TEST_SQLITE", "").lower() in {"1", "true", "yes"}:
    # Lab offline: pytest sem Postgres/docker (não usar em prod)
    _sqlite = BASE_DIR / ".storage" / "pytest_exeq.sqlite3"
    _sqlite.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(_sqlite),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "exeq_hub"),
            "USER": env("POSTGRES_USER", "exeq"),
            "PASSWORD": env("POSTGRES_PASSWORD", "exeq"),
            "HOST": env("POSTGRES_HOST", "127.0.0.1"),
            "PORT": env("POSTGRES_PORT", "5433"),
            "OPTIONS": {
                "connect_timeout": int(env("POSTGRES_CONNECT_TIMEOUT", "5") or "5"),
            },
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "pt-br"
LANGUAGES = [
    ("pt-br", "Português"),
]
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.TenantJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "apps.accounts.permissions.IsTenantMember",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "webhook_gateway": env("WEBHOOK_GATEWAY_THROTTLE", "60/min"),
        "webhook_evolution": env("WEBHOOK_EVOLUTION_THROTTLE", "120/min"),
        "cadastral_lookup": env("CADASTRO_LOOKUP_THROTTLE", "30/min"),
        "nf_issue_write": env("NF_ISSUE_WRITE_THROTTLE", "30/min"),
        "nfe_write": env("NFE_WRITE_THROTTLE", "30/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = True
# Beat: sincroniza cobranças abertas + marca vencidas. Default 4h. Requer celery beat.
CELERY_BEAT_SCHEDULE = {
    "billing-sync-open-charges": {
        "task": "billing.sync_open_charges",
        "schedule": float(env("BILLING_SYNC_INTERVAL_SECONDS", "14400") or "14400"),
        "kwargs": {"limit": int(env("BILLING_SYNC_BATCH_LIMIT", "100") or "100")},
    },
    # M5: alerta cert a vencer (<30d) → outbox certificate.expiring / .expired
    "accounts-scan-expiring-certificates": {
        "task": "accounts.scan_expiring_certificates",
        "schedule": float(env("CERT_SCAN_INTERVAL_SECONDS", "86400") or "86400"),
        "kwargs": {"alert_days": int(env("CERT_ALERT_DAYS", "30") or "30")},
    },
    # Canal WhatsApp (WA-FLX-07): expira sessões de conversa paradas
    "channel-expire-stale-sessions": {
        "task": "channel.expire_stale_sessions",
        "schedule": float(env("CHANNEL_EXPIRE_INTERVAL_SECONDS", "600") or "600"),
    },
    # RF-64: retry DANFE para NF-e authorized com pdf_pending
    "nfe-retry-pending-danfe": {
        "task": "nfe.retry_pending_danfe",
        "schedule": float(env("NFE_PDF_RETRY_INTERVAL_SECONDS", "900") or "900"),
        "kwargs": {"limit": int(env("NFE_PDF_RETRY_BATCH_LIMIT", "50") or "50")},
    },
    # RF-46: reengata poll/submitting órfãos (worker caiu)
    "nfe-reconcile-stale": {
        "task": "nfe.reconcile_stale",
        "schedule": float(env("NFE_RECONCILE_INTERVAL_SECONDS", "120") or "120"),
        "kwargs": {"limit": int(env("NFE_RECONCILE_BATCH_LIMIT", "50") or "50")},
    },
    # Food V1.1: enroll + disparos de régua de retenção
    "food-process-retention-tick": {
        "task": "food.process_retention_tick",
        "schedule": float(env("FOOD_RETENTION_INTERVAL_SECONDS", "3600") or "3600"),
    },
    # Food marketplace: poll HTTP/stub de pedidos
    "food-sync-marketplace-orders": {
        "task": "food.sync_marketplace_orders",
        "schedule": float(env("FOOD_MARKETPLACE_SYNC_INTERVAL_SECONDS", "120") or "120"),
    },
}
NF_SYNC_PROCESSING = env("NF_SYNC_PROCESSING", "false").lower() == "true"
# Reforma Tributária (NFS-e Nacional): off | shadow (calcula+snapshot, não envia) | emit
RTC_NFSEN_MODE = env("RTC_NFSEN_MODE", "shadow").strip().lower()
RTC_ENFORCE_NATIONAL_CATALOG = (
    env("RTC_ENFORCE_NATIONAL_CATALOG", "true").lower() == "true"
)
# Alíquotas-teste 2026 (ADCT / LC 214) — fração decimal (0.9% = 0.009)
RTC_TEST_CBS_RATE = env("RTC_TEST_CBS_RATE", "0.009")
RTC_TEST_IBS_RATE = env("RTC_TEST_IBS_RATE", "0.001")
# Se serviço está na Lista Nacional e não há regra com o mesmo código,
# usa regra municipal do perfil/IBGE/regime (ISS da cidade).
TAX_RULE_NATIONAL_FALLBACK = (
    env("TAX_RULE_NATIONAL_FALLBACK", "true").lower() == "true"
)
# Teto para emissões smoke/fábrica de teste (centavos). R$ 15,00 = 1500 → max 1499.
NFSE_TEST_MAX_AMOUNT_CENTS = int(env("NFSE_TEST_MAX_AMOUNT_CENTS", "1499") or "1499")
WEBHOOK_GATEWAY_SECRET = env("WEBHOOK_GATEWAY_SECRET", "dev-webhook-secret")
# Fail-closed em DEBUG=False (ou FORCE_SECURE_SECRETS=true). Ver shared/security_checks.py
FORCE_SECURE_SECRETS = env("FORCE_SECURE_SECRETS", "false").lower() == "true"
# Allowlist de IPs do originador do webhook (proxy Inter). Vazio = sem filtro (só lab).
WEBHOOK_ALLOWED_IPS = [
    ip.strip()
    for ip in env("WEBHOOK_ALLOWED_IPS", "").split(",")
    if ip.strip()
]
WEBHOOK_TRUST_X_FORWARDED_FOR = (
    env("WEBHOOK_TRUST_X_FORWARDED_FOR", "false").lower() == "true"
)
# SEC-P1-05: allowlist Admin (vazio = lab). Produção: IPs do escritório/VPN.
ADMIN_ALLOWED_IPS = [
    ip.strip()
    for ip in (env("ADMIN_ALLOWED_IPS", "") or "").split(",")
    if ip.strip()
]
ADMIN_TRUST_X_FORWARDED_FOR = (
    env("ADMIN_TRUST_X_FORWARDED_FOR", "false").lower() == "true"
)
# SEC-P1-08: sem django-cors-headers — API/Admin same-origin; não expor CORS *.
# Em multi-tenant, NÃO usar INTER_* do .env quando o tenant não tem TenantSecret.
ALLOW_ENV_INTER_CREDENTIALS_FALLBACK = (
    env("ALLOW_ENV_INTER_CREDENTIALS_FALLBACK", "true").lower() == "true"
)
PAYMENT_HTTP_MODE = env("PAYMENT_HTTP_MODE", "stub")  # stub | http
PAYMENT_DEFAULT_PROVIDER = env("PAYMENT_DEFAULT_PROVIDER", "inter")  # inter|asaas|c6
# Food Mercado Pago — override isolado do billing (FOOD_MP_HTTP_MODE vazio → PAYMENT_HTTP_MODE)
FOOD_MP_HTTP_MODE = env("FOOD_MP_HTTP_MODE", "")
FOOD_MP_WEBHOOK_SECRET = env("FOOD_MP_WEBHOOK_SECRET", "")
MERCADOPAGO_ACCESS_TOKEN = env("MERCADOPAGO_ACCESS_TOKEN", "")
MERCADOPAGO_PUBLIC_KEY = env("MERCADOPAGO_PUBLIC_KEY", "")
# Food marketplace (iFood / aiqfome) — stub | http
MARKETPLACE_HTTP_MODE = env("MARKETPLACE_HTTP_MODE", "stub")
MARKETPLACE_HTTP_TIMEOUT = float(env("MARKETPLACE_HTTP_TIMEOUT", "15") or "15")
MARKETPLACE_ORDERS_PATH = env("MARKETPLACE_ORDERS_PATH", "/orders") or "/orders"
IFOOD_API_BASE_URL = env("IFOOD_API_BASE_URL", "")
IFOOD_API_TOKEN = env("IFOOD_API_TOKEN", "")
AIQFOME_API_BASE_URL = env("AIQFOME_API_BASE_URL", "")
AIQFOME_API_TOKEN = env("AIQFOME_API_TOKEN", "")
ASAAS_API_TOKEN = env("ASAAS_API_TOKEN", "")
ASAAS_API_BASE_URL = env(
    "ASAAS_API_BASE_URL",
    "https://sandbox.asaas.com/api/v3",
)
# Inter Cobrança v3 (BolePix) — https://developers.inter.co/references/cobranca-bolepix
INTER_API_BASE_URL = env(
    "INTER_API_BASE_URL",
    "https://cdpj-sandbox.partners.uatinter.co",
)
INTER_API_TOKEN = env("INTER_API_TOKEN", "")
INTER_CLIENT_ID = env("INTER_CLIENT_ID", "")
INTER_CLIENT_SECRET = env("INTER_CLIENT_SECRET", "")
INTER_CERT_PATH = env("INTER_CERT_PATH", "")
INTER_KEY_PATH = env("INTER_KEY_PATH", "")
INTER_CERT_PEM = env("INTER_CERT_PEM", "")
INTER_KEY_PEM = env("INTER_KEY_PEM", "")
INTER_CONTA_CORRENTE = env("INTER_CONTA_CORRENTE", "")
INTER_OAUTH_TOKEN_PATH = env("INTER_OAUTH_TOKEN_PATH", "/oauth/v2/token")
INTER_OAUTH_SCOPE = env(
    "INTER_OAUTH_SCOPE",
    "boleto-cobranca.read boleto-cobranca.write",
)
INTER_CHARGE_PATH = env("INTER_CHARGE_PATH", "/cobranca/v3/cobrancas")
INTER_CANCEL_PATH_TMPL = env(
    "INTER_CANCEL_PATH_TMPL",
    "/cobranca/v3/cobrancas/{ref}/cancelar",
)
INTER_CANCEL_MOTIVO = env("INTER_CANCEL_MOTIVO", "ACERTOS")
INTER_NUM_DIAS_AGENDA = int(env("INTER_NUM_DIAS_AGENDA", "0") or "0")
# URL HTTPS pública do Hub para o Inter chamar (D1). Ex.: https://hub.exemplo.com/api/v1/webhooks/gateway
INTER_WEBHOOK_PUBLIC_URL = env("INTER_WEBHOOK_PUBLIC_URL", "")
INTER_WEBHOOK_PATH = env("INTER_WEBHOOK_PATH", "/cobranca/v3/cobrancas/webhook")
INTER_WEBHOOK_RETRY_MAX = int(env("INTER_WEBHOOK_RETRY_MAX", "50") or "50")
# C6 BaaS bank_slips — https://developers.c6bank.com.br/
C6_API_BASE_URL = env(
    "C6_API_BASE_URL",
    "https://baas-api-sandbox.c6bank.info",
)
C6_API_TOKEN = env("C6_API_TOKEN", "")
C6_CHARGE_PATH = env("C6_CHARGE_PATH", "/v1/bank_slips")
C6_CANCEL_PATH_TMPL = env("C6_CANCEL_PATH_TMPL", "/v1/bank_slips/{ref}/cancel")
C6_BILLING_SCHEME = env("C6_BILLING_SCHEME", "21")  # 21 sandbox / 15 produção (guia C6)
C6_PAYER_STREET = env("C6_PAYER_STREET", "NAO INFORMADO")
C6_PAYER_NUMBER = env("C6_PAYER_NUMBER", "S/N")
C6_PAYER_CITY = env("C6_PAYER_CITY", "SAO PAULO")
C6_PAYER_STATE = env("C6_PAYER_STATE", "SP")
C6_PAYER_ZIP = env("C6_PAYER_ZIP", "01000000")
FOCUS_WEBHOOK_SECRET = env("FOCUS_WEBHOOK_SECRET", "dev-focus-webhook-secret")
FOCUS_WEBHOOK_PUBLIC_URL = env("FOCUS_WEBHOOK_PUBLIC_URL", "")
FOCUS_MUNICIPIO_CACHE_TTL = int(env("FOCUS_MUNICIPIO_CACHE_TTL", "86400") or "86400")
# MVP emissor próprio: sefin (RF-51). Focus só com override lab / NFSE_DEFAULT_PROVIDER=focus.
NFSE_DEFAULT_PROVIDER = env("NFSE_DEFAULT_PROVIDER", "sefin")  # sefin | focus | betha
NFSE_DEFAULT_LAYOUT = env("NFSE_DEFAULT_LAYOUT", "nfsen")  # nfse | nfsen (legado Focus)
NFSE_BETHA_IBGE_CODES = env("NFSE_BETHA_IBGE_CODES", "")
NFSE_NATIONAL_IBGE_CODES = env("NFSE_NATIONAL_IBGE_CODES", "3504107")  # semente produção (Atibaia+)
NFSE_NATIONAL_MANDATORY_FROM = env("NFSE_NATIONAL_MANDATORY_FROM", "2026-09-01")
# RF-01: stub = cache semente por ambiente; http = ADN parametros_municipais/.../convenio
NFSE_CONVENIO_MODE = env("NFSE_CONVENIO_MODE", "stub")  # stub | http
NFSE_CONVENIO_CACHE_SECONDS = int(env("NFSE_CONVENIO_CACHE_SECONDS", "21600") or "21600")
NFSE_CONVENIO_DENY_IBGE = env("NFSE_CONVENIO_DENY_IBGE", "")  # lab/QA: forçar bloqueio
# Homolog/produção restrita: default vazio (Atibaia sem convênio útil em restrita — estudo PO).
NFSE_CONVENIO_HOMOLOG_IBGE_CODES = env("NFSE_CONVENIO_HOMOLOG_IBGE_CODES", "")
ADN_PARAM_BASE_URL = env("ADN_PARAM_BASE_URL", "")
SEFIN_HTTP_MODE = env("SEFIN_HTTP_MODE", "stub")  # stub | http (mTLS M2+)
SEFIN_ENVIRONMENT = env("SEFIN_ENVIRONMENT", "homolog")  # homolog | production
SEFIN_BASE_URL = env("SEFIN_BASE_URL", "")  # override opcional da base SefinNacional
SEFIN_BASE_URL_HOMOLOG = env(
    "SEFIN_BASE_URL_HOMOLOG",
    "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
)
SEFIN_BASE_URL_PROD = env(
    "SEFIN_BASE_URL_PROD",
    "https://sefin.nfse.gov.br/SefinNacional",
)
# SEC-P1-07: retry só transporte/5xx; 4xx nunca repete.
SEFIN_HTTP_TIMEOUT_SECONDS = float(env("SEFIN_HTTP_TIMEOUT_SECONDS", "45") or "45")
SEFIN_HTTP_MAX_ATTEMPTS = int(env("SEFIN_HTTP_MAX_ATTEMPTS", "3") or "3")
SEFIN_HTTP_RETRY_BACKOFF_SECONDS = float(
    env("SEFIN_HTTP_RETRY_BACKOFF_SECONDS", "0.5") or "0.5"
)
# SEC-P2-04: teto Celery (0 = calcular a partir do budget HTTP).
NFSE_PROCESS_SOFT_TIME_LIMIT = int(env("NFSE_PROCESS_SOFT_TIME_LIMIT", "0") or "0") or None
NFSE_PROCESS_HARD_TIME_LIMIT = int(env("NFSE_PROCESS_HARD_TIME_LIMIT", "0") or "0") or None
NFSE_POLL_SOFT_TIME_LIMIT = int(env("NFSE_POLL_SOFT_TIME_LIMIT", "0") or "0") or None
NFSE_POLL_HARD_TIME_LIMIT = int(env("NFSE_POLL_HARD_TIME_LIMIT", "0") or "0") or None
DANFSE_LAYOUT_VERSION = env("DANFSE_LAYOUT_VERSION", "nt008-v1.02")

# NF-e produto (ADR-NFE-001) — default off; lab: NFE_ENABLED=true + NFE_HTTP_MODE=stub
NFE_ENABLED = (env("NFE_ENABLED", "false") or "false").lower() in ("1", "true", "yes")
NFE_HTTP_MODE = env("NFE_HTTP_MODE", "stub")  # stub | http (SEFAZ-SP)
NFE_HTTP_DRY_RUN = (env("NFE_HTTP_DRY_RUN", "false") or "false").lower() in ("1", "true", "yes")
NFE_HTTP_TIMEOUT = int(env("NFE_HTTP_TIMEOUT", "60") or "60")
NFE_DEFAULT_TP_AMB = env("NFE_DEFAULT_TP_AMB", "2")  # 2 homolog | 1 produção
NFE_LAYOUT_VERSION = env("NFE_LAYOUT_VERSION", "pl009-stub")
NFE_PIVOT_UF = env("NFE_PIVOT_UF", "SP")
# I5: reconciliação polling → authorized|rejected|failed
NFE_POLL_COUNTDOWN = int(env("NFE_POLL_COUNTDOWN", "15") or "15")
NFE_POLL_MAX_ATTEMPTS = int(env("NFE_POLL_MAX_ATTEMPTS", "12") or "12")
NFE_SYNC_POLL = (env("NFE_SYNC_POLL", "false") or "false").lower() in ("1", "true", "yes")
# RF-46: invoice em polling/submitting sem task ativa há N segundos → reconcilia
NFE_RECONCILE_STALE_SECONDS = int(env("NFE_RECONCILE_STALE_SECONDS", "120") or "120")
# RF-41: path opcional para XSD oficial (vazio = só preflight estrutural)
NFE_XSD_PATH = env("NFE_XSD_PATH", "")

FOCUS_HTTP_MODE = env("FOCUS_HTTP_MODE", "stub")  # stub | http
FOCUS_API_BASE_URL = env(
    "FOCUS_API_BASE_URL",
    "https://homologacao.focusnfe.com.br",
)
FOCUS_API_TOKEN = env("FOCUS_API_TOKEN", "")  # never commit real tokens
RECEITA_HTTP_MODE = env("RECEITA_HTTP_MODE", "stub")  # stub | http (SERPRO)
# Consulta cadastral CNPJ (separada de DAS/DARF). stub | http
CADASTRO_HTTP_MODE = env("CADASTRO_HTTP_MODE", "http")
CADASTRO_CNPJ_PROVIDER = env("CADASTRO_CNPJ_PROVIDER", "brasilapi")
CADASTRO_CNPJ_BASE_URL = env(
    "CADASTRO_CNPJ_BASE_URL",
    "https://brasilapi.com.br/api/cnpj/v1",
)
CADASTRO_CNPJ_API_TOKEN = env("CADASTRO_CNPJ_API_TOKEN", "")
CADASTRO_CNPJ_TIMEOUT = float(env("CADASTRO_CNPJ_TIMEOUT", "3") or "3")
CADASTRO_CEP_BASE_URL = env("CADASTRO_CEP_BASE_URL", "https://viacep.com.br/ws")
CADASTRO_LOOKUP_CACHE_HOURS = int(env("CADASTRO_LOOKUP_CACHE_HOURS", "24") or "24")

SERPRO_AUTH_URL = env(
    "SERPRO_AUTH_URL",
    "https://autenticacao.sapi.serpro.gov.br/authenticate",
)
SERPRO_GATEWAY_URL = env(
    "SERPRO_GATEWAY_URL",
    "https://gateway.apiserpro.serpro.gov.br/integra-contador/v1",
)
SERPRO_ROLE_TYPE = env("SERPRO_ROLE_TYPE", "TERCEIROS")
SERPRO_EMIT_PATH = env("SERPRO_EMIT_PATH", "Emitir")
SERPRO_ID_SISTEMA_DAS = env("SERPRO_ID_SISTEMA_DAS", "PGDASD")
SERPRO_ID_SERVICO_GERAR_DAS = env("SERPRO_ID_SERVICO_GERAR_DAS", "GERARDAS12")
SERPRO_ID_SERVICO_GERAR_DARF = env("SERPRO_ID_SERVICO_GERAR_DARF", "")
SERPRO_VERSAO_SISTEMA = env("SERPRO_VERSAO_SISTEMA", "1.0")
SERPRO_CONSUMER_KEY = env("SERPRO_CONSUMER_KEY", "")
SERPRO_CONSUMER_SECRET = env("SERPRO_CONSUMER_SECRET", "")
DAS_REQUIRE_ELECTRONIC_PROXY = (
    env("DAS_REQUIRE_ELECTRONIC_PROXY", "false").lower() == "true"
)
STORAGE_BACKEND = env("STORAGE_BACKEND", "local")
LOCAL_STORAGE_ROOT = env("LOCAL_STORAGE_ROOT", str(BASE_DIR / ".storage"))
FIELD_ENCRYPTION_KEY = env(
    "FIELD_ENCRYPTION_KEY",
    # Apenas lab/DEBUG. Produção: obrigatório override (security_checks).
    "n_AQ8FIJHEVdMys3lkm17BygqS8UkBCEfRtzlNaZhhw=",
)
FOCUS_POLL_COUNTDOWN = int(env("FOCUS_POLL_COUNTDOWN", "15") or "15")
EVOLUTION_HTTP_MODE = env("EVOLUTION_HTTP_MODE", "stub")  # stub | http
EVOLUTION_API_BASE_URL = env("EVOLUTION_API_BASE_URL", "")
EVOLUTION_API_KEY = env("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = env("EVOLUTION_INSTANCE", "")
# Fase 3 (WA-SEC): token do webhook Evolution (header X-Exeq-Webhook-Token ou apikey).
# Vazio = rejeita todos os POSTs (fail-closed).
EVOLUTION_WEBHOOK_TOKEN = env("EVOLUTION_WEBHOOK_TOKEN", "")
# Lab: aceita payload simplificado {tenant_slug, phone_e164, message_id, text}.
# Produção: false — só payload nativo com tenant via settings.evolution_instance.
EVOLUTION_WEBHOOK_ALLOW_LEGACY = (
    env("EVOLUTION_WEBHOOK_ALLOW_LEGACY", "true").lower() == "true"
)
# Provedor WhatsApp global: evolution (não oficial) | meta (Cloud API oficial).
# Override por tenant: tenant.settings["whatsapp_provider"].
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", "evolution")
# Canal WhatsApp: TTL da sessão de conversa (WA-FLX-07)
CHANNEL_SESSION_TTL_MINUTES = int(env("CHANNEL_SESSION_TTL_MINUTES", "30") or "30")
# WA-IA: stub (heurística lab) | off (só fluxo guiado) | http (LLM futuro)
CHANNEL_AI_MODE = env("CHANNEL_AI_MODE", "stub")
META_WHATSAPP_HTTP_MODE = env("META_WHATSAPP_HTTP_MODE", "stub")  # stub | http
META_WHATSAPP_TOKEN = env("META_WHATSAPP_TOKEN", "")
META_WHATSAPP_PHONE_NUMBER_ID = env("META_WHATSAPP_PHONE_NUMBER_ID", "")
META_GRAPH_API_VERSION = env("META_GRAPH_API_VERSION", "v23.0")
RLS_SUBJECT_ROLE = env("RLS_SUBJECT_ROLE", "exeq_app")

# Admin Django = clássico (sem Unfold). UI operacional do cliente = Hub V4 em /hub/.

# E-mail (convites Hub, NF-e RF-71). Lab default: console.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "25") or "25")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = (env("EMAIL_USE_TLS", "false") or "false").lower() in (
    "1",
    "true",
    "yes",
)
EMAIL_USE_SSL = (env("EMAIL_USE_SSL", "false") or "false").lower() in (
    "1",
    "true",
    "yes",
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "EXEQ Hub <noreply@exeq.local>")
SERVER_EMAIL = env("SERVER_EMAIL", DEFAULT_FROM_EMAIL)