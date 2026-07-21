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
ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1", "testserver"]

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
    "apps.billing",
    "apps.das",
    "apps.channel",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "shared.middleware.TenantRLSMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "exeq_hub"),
        "USER": env("POSTGRES_USER", "exeq"),
        "PASSWORD": env("POSTGRES_PASSWORD", "exeq"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "5433"),
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.TenantJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "apps.accounts.permissions.IsTenantMember",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = True
NF_SYNC_PROCESSING = env("NF_SYNC_PROCESSING", "false").lower() == "true"
WEBHOOK_GATEWAY_SECRET = env("WEBHOOK_GATEWAY_SECRET", "dev-webhook-secret")
PAYMENT_HTTP_MODE = env("PAYMENT_HTTP_MODE", "stub")  # stub | http
PAYMENT_DEFAULT_PROVIDER = env("PAYMENT_DEFAULT_PROVIDER", "inter")  # inter|asaas|c6
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
NFSE_DEFAULT_PROVIDER = env("NFSE_DEFAULT_PROVIDER", "focus")
NFSE_DEFAULT_LAYOUT = env("NFSE_DEFAULT_LAYOUT", "nfsen")  # nfse | nfsen
NFSE_BETHA_IBGE_CODES = env("NFSE_BETHA_IBGE_CODES", "")
NFSE_NATIONAL_IBGE_CODES = env("NFSE_NATIONAL_IBGE_CODES", "3504107")  # Atibaia+
NFSE_NATIONAL_MANDATORY_FROM = env("NFSE_NATIONAL_MANDATORY_FROM", "2026-09-01")
FOCUS_HTTP_MODE = env("FOCUS_HTTP_MODE", "stub")  # stub | http
FOCUS_API_BASE_URL = env(
    "FOCUS_API_BASE_URL",
    "https://homologacao.focusnfe.com.br",
)
FOCUS_API_TOKEN = env("FOCUS_API_TOKEN", "")  # never commit real tokens
RECEITA_HTTP_MODE = env("RECEITA_HTTP_MODE", "stub")  # stub | http (SERPRO)
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
    "n_AQ8FIJHEVdMys3lkm17BygqS8UkBCEfRtzlNaZhhw=",
)
FOCUS_POLL_COUNTDOWN = int(env("FOCUS_POLL_COUNTDOWN", "15") or "15")
EVOLUTION_HTTP_MODE = env("EVOLUTION_HTTP_MODE", "stub")  # stub | http
EVOLUTION_API_BASE_URL = env("EVOLUTION_API_BASE_URL", "")
EVOLUTION_API_KEY = env("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = env("EVOLUTION_INSTANCE", "")
RLS_SUBJECT_ROLE = env("RLS_SUBJECT_ROLE", "exeq_app")
