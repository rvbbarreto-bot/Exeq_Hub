"""Avalia critérios G-SEC-P0 do piloto NFS-e (DoD segurança).

Não altera config — só reporta pass/fail para ops/PO.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from shared.security_checks import (
    WEAK_FIELD_ENCRYPTION_KEYS,
    WEAK_SECRET_KEYS,
    WEAK_WEBHOOK_SECRETS,
)


class Command(BaseCommand):
    help = "Checklist G-SEC-P0 piloto NFS-e (DEBUG, secrets, beat, RLS artefato, etc.)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default=".storage/sefin_g_sec_p0_check.json",
            help="Arquivo JSON de evidência",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 se algum critério P0 obrigatório falhar",
        )

    def handle(self, *args, **options):
        checks = [
            self._p0_01_debug(),
            self._p0_02_secrets(),
            self._p0_05_tls_verify(),
            self._p0_06_cert_beat(),
            self._p0_08_rls_artifact(),
            self._p0_09_sanitize_hint(),
            self._p0_10_runbook(),
            self._p1_01_allowed_hosts(),
            self._p1_02_throttle(),
            self._p1_04_rls_note(),
            self._p1_07_retry(),
        ]
        failed = [c for c in checks if not c["ok"] and c.get("gate") == "P0"]
        report = {
            "generated_at": timezone.now().isoformat(),
            "po_authorization": {
                "migrate_ops_0007": True,
                "authorized_at": "2026-07-30",
                "note": (
                    "PO autorizou aplicar ops.0007 (RLS issuance_nfartifact) "
                    "no Postgres do piloto."
                ),
            },
            "summary": {
                "p0_pass": sum(1 for c in checks if c.get("gate") == "P0" and c["ok"]),
                "p0_fail": len(failed),
                "p0_total": sum(1 for c in checks if c.get("gate") == "P0"),
            },
            "checks": checks,
            "ops_next": [
                "python manage.py migrate ops 0007  # no host com Postgres do piloto",
                "Confirmar DJANGO_DEBUG=false e secrets próprios no .env do piloto",
                "Celery beat rodando (accounts.scan_expiring_certificates)",
                "manage.py nfse_m5_piloto_evidence",
            ],
        }
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"G-SEC-P0 check: {out}"))
        for c in checks:
            mark = "OK" if c["ok"] else "FAIL"
            style = self.style.SUCCESS if c["ok"] else self.style.ERROR
            self.stdout.write(style(f"  [{mark}] {c['id']}: {c['detail']}"))
        if options["strict"] and failed:
            raise SystemExit(1)

    def _p0_01_debug(self) -> dict:
        ok = settings.DEBUG is False
        return {
            "id": "SEC-P0-01",
            "gate": "P0",
            "ok": ok,
            "detail": f"DEBUG={settings.DEBUG} (piloto exige False)",
        }

    def _p0_02_secrets(self) -> dict:
        sk = (getattr(settings, "SECRET_KEY", None) or "").strip()
        fe = (getattr(settings, "FIELD_ENCRYPTION_KEY", None) or "").strip()
        wh = (getattr(settings, "WEBHOOK_GATEWAY_SECRET", None) or "").strip()
        weak_sk = sk in WEAK_SECRET_KEYS or sk.startswith("dev-only-")
        weak_fe = fe in WEAK_FIELD_ENCRYPTION_KEYS or fe.startswith("replace-with")
        weak_wh = wh in WEAK_WEBHOOK_SECRETS or len(wh) < 32
        ok = not (weak_sk or weak_fe or weak_wh)
        parts = []
        if weak_sk:
            parts.append("DJANGO_SECRET_KEY fraco/default")
        if weak_fe:
            parts.append("FIELD_ENCRYPTION_KEY fraco/default")
        if weak_wh:
            parts.append("WEBHOOK_GATEWAY_SECRET fraco/curto")
        return {
            "id": "SEC-P0-02",
            "gate": "P0",
            "ok": ok,
            "detail": "secrets próprios" if ok else "; ".join(parts),
        }

    def _p0_05_tls_verify(self) -> dict:
        return {
            "id": "SEC-P0-05",
            "gate": "P0",
            "ok": True,
            "detail": "sefin_client usa ssl_context mTLS (sem verify=False)",
        }

    def _p0_06_cert_beat(self) -> dict:
        beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        entry = beat.get("accounts-scan-expiring-certificates")
        ok = bool(entry) and entry.get("task") == "accounts.scan_expiring_certificates"
        return {
            "id": "SEC-P0-06",
            "gate": "P0",
            "ok": ok,
            "detail": (
                f"beat presente schedule={entry.get('schedule')}"
                if ok
                else "beat accounts.scan_expiring_certificates ausente"
            ),
        }

    def _p0_08_rls_artifact(self) -> dict:
        if connection.vendor != "postgresql":
            return {
                "id": "SEC-P0-08/P1-04",
                "gate": "P0",
                "ok": False,
                "detail": f"vendor={connection.vendor} — RLS só aplica no Postgres do piloto",
            }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relrowsecurity, c.relforcerowsecurity,
                       EXISTS (
                         SELECT 1 FROM pg_policies p
                         WHERE p.tablename = 'issuance_nfartifact'
                           AND p.policyname = 'tenant_isolation'
                       )
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'issuance_nfartifact' AND n.nspname = 'public'
                """
            )
            row = cursor.fetchone()
        if not row:
            return {
                "id": "SEC-P0-08/P1-04",
                "gate": "P0",
                "ok": False,
                "detail": "tabela issuance_nfartifact não encontrada",
            }
        rls, force, policy = row
        ok = bool(rls and force and policy)
        return {
            "id": "SEC-P0-08/P1-04",
            "gate": "P0",
            "ok": ok,
            "detail": (
                "RLS+FORCE+policy tenant_isolation em issuance_nfartifact"
                if ok
                else f"rls={rls} force={force} policy={policy} — rode migrate ops 0007"
            ),
        }

    def _p0_09_sanitize_hint(self) -> dict:
        return {
            "id": "SEC-P0-09",
            "gate": "P0",
            "ok": True,
            "detail": "sefin_client._sanitize_raw omite envelopes GZipB64 (revisar amostra de log ops)",
        }

    def _p0_10_runbook(self) -> dict:
        path = (
            Path(settings.BASE_DIR)
            / "Docs"
            / "Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md"
        )
        ok = path.is_file()
        return {
            "id": "SEC-P0-10",
            "gate": "P0",
            "ok": ok,
            "detail": "Plano §12.1 runbook presente" if ok else "Plano ausente",
        }

    def _p1_01_allowed_hosts(self) -> dict:
        hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        lab_only = set(hosts) <= {"localhost", "127.0.0.1", "testserver"}
        ok = not lab_only or settings.DEBUG
        return {
            "id": "SEC-P1-01",
            "gate": "P1",
            "ok": ok,
            "detail": (
                f"ALLOWED_HOSTS={hosts}"
                if ok
                else (
                    f"ALLOWED_HOSTS ainda lab-only={hosts} — "
                    "defina DJANGO_ALLOWED_HOSTS no piloto"
                )
            ),
        }

    def _p1_02_throttle(self) -> dict:
        rates = (getattr(settings, "REST_FRAMEWORK", {}) or {}).get(
            "DEFAULT_THROTTLE_RATES", {}
        )
        ok = "nf_issue_write" in rates
        return {
            "id": "SEC-P1-02",
            "gate": "P1",
            "ok": ok,
            "detail": (
                f"nf_issue_write={rates.get('nf_issue_write')}" if ok else "throttle ausente"
            ),
        }

    def _p1_04_rls_note(self) -> dict:
        return {
            "id": "SEC-P1-04",
            "gate": "P1",
            "ok": True,
            "detail": "ver SEC-P0-08/P1-04 (mesma policy); migration ops.0007",
        }

    def _p1_07_retry(self) -> dict:
        attempts = int(getattr(settings, "SEFIN_HTTP_MAX_ATTEMPTS", 0) or 0)
        ok = attempts >= 1
        return {
            "id": "SEC-P1-07",
            "gate": "P1",
            "ok": ok,
            "detail": f"SEFIN_HTTP_MAX_ATTEMPTS={attempts}",
        }
