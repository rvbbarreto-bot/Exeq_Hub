"""Checklist de prontidão — Mercado Pago Pix Food (piloto 27/08/2026)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.accounts.secrets import get_tenant_secret_plaintext
from apps.food.models import FoodCustomer
from apps.food.payments.mercadopago.client import get_access_token, resolve_mp_http_mode


class Command(BaseCommand):
    help = (
        "Checklist MP Food: .env, tenant settings, TenantSecret, cliente e-mail, "
        "opcional probe HTTP na API Mercado Pago."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="food-qa")
        parser.add_argument(
            "--probe-http",
            action="store_true",
            help="GET /users/me na API MP (exige access_token configurado).",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 se algum item obrigatório falhar.",
        )
        parser.add_argument(
            "--out",
            default=".storage/food_mp_check.json",
            help="JSON de evidência",
        )
        parser.add_argument(
            "--public-base-url",
            default="",
            help="URL pública para webhook (ex.: https://abc.ngrok-free.app).",
        )

    def handle(self, *args, **options):
        slug = (options["tenant"] or "food-qa").strip()
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant não encontrado: {slug}") from exc

        public_base = (options["public_base_url"] or "").strip().rstrip("/")
        checks = [
            self._check_field_encryption(),
            self._check_env_http_mode(),
            self._check_webhook_secret_env(),
            self._check_tenant_settings(tenant),
            self._check_tenant_secrets(tenant),
            self._check_customer_email(tenant),
            self._check_webhook_url(public_base),
        ]
        if options["probe_http"]:
            checks.append(self._probe_mp_api(tenant))

        failed = [c for c in checks if not c["ok"]]
        report = {
            "generated_at": timezone.now().isoformat(),
            "tenant_slug": slug,
            "mp_http_mode": resolve_mp_http_mode(),
            "payment_http_mode": getattr(settings, "PAYMENT_HTTP_MODE", ""),
            "summary": {
                "pass": sum(1 for c in checks if c["ok"]),
                "fail": len(failed),
                "total": len(checks),
            },
            "checks": checks,
            "next_steps": self._next_steps(checks, public_base=public_base),
        }
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Food MP check: {out}"))
        for c in checks:
            mark = "OK" if c["ok"] else "FAIL"
            style = self.style.SUCCESS if c["ok"] else self.style.ERROR
            self.stdout.write(style(f"  [{mark}] {c['id']}: {c['detail']}"))
        if options["strict"] and failed:
            raise SystemExit(1)

    def _check_field_encryption(self) -> dict[str, Any]:
        key = (getattr(settings, "FIELD_ENCRYPTION_KEY", None) or "").strip()
        ok = bool(key) and not key.startswith("replace-with")
        return {
            "id": "MP-02-FIELD_ENCRYPTION",
            "ok": ok,
            "detail": "FIELD_ENCRYPTION_KEY configurada" if ok else "FIELD_ENCRYPTION_KEY ausente/placeholder",
        }

    def _check_env_http_mode(self) -> dict[str, Any]:
        mp_mode = resolve_mp_http_mode()
        pay_mode = (getattr(settings, "PAYMENT_HTTP_MODE", "stub") or "stub").lower()
        ok_stub_lab = mp_mode == "stub" and bool(
            (getattr(settings, "FOOD_MP_WEBHOOK_SECRET", "") or "").strip()
        )
        ok_http = mp_mode == "http" and pay_mode == "http"
        ok = ok_stub_lab or ok_http
        if ok_http:
            detail = "FOOD_MP_HTTP_MODE=http + PAYMENT_HTTP_MODE=http"
        elif ok_stub_lab:
            detail = "Lab stub: FOOD_MP_HTTP_MODE=stub + FOOD_MP_WEBHOOK_SECRET"
        else:
            detail = (
                f"Modo inconsistente: FOOD_MP_HTTP_MODE={mp_mode}, "
                f"PAYMENT_HTTP_MODE={pay_mode}"
            )
        return {"id": "MP-02-ENV-MODE", "ok": ok, "detail": detail}

    def _check_webhook_secret_env(self) -> dict[str, Any]:
        secret = (getattr(settings, "FOOD_MP_WEBHOOK_SECRET", "") or "").strip()
        ok = len(secret) >= 8
        return {
            "id": "MP-02-WEBHOOK-SECRET",
            "ok": ok,
            "detail": "FOOD_MP_WEBHOOK_SECRET definido" if ok else "FOOD_MP_WEBHOOK_SECRET vazio",
        }

    def _check_tenant_settings(self, tenant: Tenant) -> dict[str, Any]:
        s = tenant.settings or {}
        provider = s.get("food_payment_provider")
        methods = s.get("food_payment_methods_enabled") or []
        ok = provider == "mercadopago" and "pix" in methods
        return {
            "id": "MP-03-TENANT-SETTINGS",
            "ok": ok,
            "detail": (
                f"food_payment_provider={provider}, methods={methods}"
                if ok
                else f"Esperado mercadopago + pix; got provider={provider}, methods={methods}"
            ),
        }

    def _check_tenant_secrets(self, tenant: Tenant) -> dict[str, Any]:
        mp_mode = resolve_mp_http_mode()
        token = get_tenant_secret_plaintext(
            tenant=tenant, provider="mercadopago", key_name="access_token"
        ) or (getattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "") or "").strip()
        pub = get_tenant_secret_plaintext(
            tenant=tenant, provider="mercadopago", key_name="public_key"
        ) or (getattr(settings, "MERCADOPAGO_PUBLIC_KEY", "") or "").strip()
        wh = get_tenant_secret_plaintext(
            tenant=tenant, provider="mercadopago", key_name="webhook_secret"
        ) or (getattr(settings, "FOOD_MP_WEBHOOK_SECRET", "") or "").strip()

        if mp_mode == "stub":
            ok = bool(wh)
            detail = "stub: webhook_secret OK (tenant ou .env)"
            if not ok:
                detail = "stub: falta webhook_secret"
        else:
            ok = bool(token) and bool(pub) and bool(wh)
            parts = []
            if not token:
                parts.append("access_token")
            if not pub:
                parts.append("public_key")
            if not wh:
                parts.append("webhook_secret")
            detail = (
                "HTTP: credenciais MP completas"
                if ok
                else f"HTTP: faltam {', '.join(parts)}"
            )
        return {"id": "MP-04-TENANT-SECRETS", "ok": ok, "detail": detail}

    def _check_customer_email(self, tenant: Tenant) -> dict[str, Any]:
        count = FoodCustomer.objects.filter(tenant=tenant).exclude(email="").count()
        ok = count >= 1
        return {
            "id": "MP-06-CUSTOMER-EMAIL",
            "ok": ok,
            "detail": f"{count} cliente(s) Food com e-mail" if ok else "Nenhum cliente com e-mail",
        }

    def _check_webhook_url(self, public_base: str) -> dict[str, Any]:
        path = "/api/v1/food/webhooks/mercadopago"
        if public_base:
            url = f"{public_base}{path}"
            ok = public_base.startswith("https://")
            detail = f"Webhook URL: {url}"
        else:
            ok = True
            detail = (
                f"Webhook local (ngrok): https://<dominio>{path} — "
                "passe --public-base-url após ngrok"
            )
        return {"id": "MP-05-WEBHOOK-URL", "ok": ok, "detail": detail}

    def _probe_mp_api(self, tenant: Tenant) -> dict[str, Any]:
        if resolve_mp_http_mode() != "http":
            return {
                "id": "MP-PROBE-HTTP",
                "ok": False,
                "detail": "Probe ignorado: FOOD_MP_HTTP_MODE != http",
            }
        token = get_access_token(tenant=tenant)
        if not token:
            return {
                "id": "MP-PROBE-HTTP",
                "ok": False,
                "detail": "Sem access_token para probe",
            }
        try:
            resp = httpx.get(
                "https://api.mercadopago.com/users/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            return {
                "id": "MP-PROBE-HTTP",
                "ok": False,
                "detail": f"Rede MP: {exc}",
            }
        ok = resp.status_code == 200
        snippet = resp.text[:120] if not ok else "users/me OK"
        return {
            "id": "MP-PROBE-HTTP",
            "ok": ok,
            "detail": f"HTTP {resp.status_code}: {snippet}",
        }

    def _next_steps(
        self, checks: list[dict[str, Any]], *, public_base: str
    ) -> list[str]:
        steps: list[str] = []
        by_id = {c["id"]: c for c in checks}
        if not by_id.get("MP-04-TENANT-SECRETS", {}).get("ok"):
            steps.append(
                "python manage.py food_onboard_qa "
                "--mp-access-token TEST-... --mp-public-key TEST-... "
                "--mp-webhook-secret <secret-painel-mp>"
            )
        if resolve_mp_http_mode() == "stub":
            steps.append(
                "Sandbox: .env → FOOD_MP_HTTP_MODE=http + MERCADOPAGO_* TEST; reiniciar runserver"
            )
        if not public_base:
            steps.append("ngrok http 8000 → cadastrar URL no painel MP (evento payment)")
        steps.append(
            "Teste Hub: /hub/food/pedidos/novo/ → detalhe → Gerar Pix → pagar sandbox"
        )
        return steps
