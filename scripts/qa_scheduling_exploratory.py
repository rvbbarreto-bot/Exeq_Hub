"""
Roteiro exploratório QA — EXEQ Agendador (API).
Executar após: python manage.py seed_scheduling_qa
Uso: python scripts/qa_scheduling_exploratory.py [--base-url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from typing import Any

import httpx

TENANT = "agendador-qa"
EMAIL = "agenda.qa@exeq.local"
PASSWORD = "AgendaQa123!"
PROFESSIONAL_ID = "aaaaaaaa-bbbb-4ccc-8ddd-333333333333"
CUSTOMER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-222222222222"
SERVICE_CORTE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-444444444444"


class Findings:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.bugs: list[str] = []
        self.notes: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed.append(msg)

    def fail(self, msg: str) -> None:
        self.failed.append(msg)

    def bug(self, msg: str) -> None:
        self.bugs.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def _next_weekday_slot(hour: int = 10, minute: int = 0) -> datetime:
    tz = ZoneInfo("America/Sao_Paulo")
    day = datetime.now(tz).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


def login(client: httpx.Client, base: str, findings: Findings) -> str | None:
    r = client.post(
        f"{base}/api/v1/auth/login",
        json={"tenant_slug": TENANT, "email": EMAIL, "password": PASSWORD},
    )
    if r.status_code != 200:
        findings.fail(f"Login falhou HTTP {r.status_code}: {r.text[:300]}")
        return None
    token = r.json().get("access")
    if not token:
        findings.fail("Login 200 sem access token")
        return None
    findings.ok("Login tenant agendador-qa")
    return token


def check_required_fields(client: httpx.Client, findings: Findings) -> None:
    # POST appointment sem body
    r = client.post("/api/v1/scheduling/appointments/", json={})
    if r.status_code in (400, 422):
        findings.ok(f"POST appointment vazio -> {r.status_code} (validacao)")
        data = r.json()
        fields = set(data.keys()) - {"detail", "code"}
        if not fields and "detail" in data:
            findings.note(f"Resposta validacao appointment: {json.dumps(data)[:400]}")
        else:
            findings.ok(f"Campos rejeitados no body vazio: {sorted(fields)}")
    else:
        findings.bug(f"POST appointment vazio deveria 400/422, veio {r.status_code}")

    # professional sem name
    r = client.post(
        "/api/v1/scheduling/professionals/",
        json={"provider": "aaaaaaaa-bbbb-4ccc-8ddd-111111111111"},
    )
    if r.status_code in (400, 422):
        findings.ok(f"POST professional sem name -> {r.status_code}")
    else:
        findings.bug(f"POST professional sem name -> {r.status_code} (esperado 400)")

    # service duration inválida
    r = client.post(
        "/api/v1/scheduling/services/",
        json={"name": "X", "duration_minutes": 1, "price_cents": 100},
    )
    if r.status_code in (400, 422):
        findings.ok("POST service duration=1 rejeitado na API")
    elif r.status_code >= 500:
        findings.bug(
            f"POST service duration=1 -> HTTP {r.status_code} "
            "(constraint DB sem validacao serializer — UX ruim)"
        )
    else:
        findings.bug(f"POST service duration=1 aceito ({r.status_code}) — deveria falhar")


def check_happy_path(client: httpx.Client, findings: Findings) -> str | None:
    day = _next_weekday_slot().date()
    av = client.get(
        "/api/v1/scheduling/availability",
        params={
            "professional_id": PROFESSIONAL_ID,
            "service_id": SERVICE_CORTE_ID,
            "day": day.isoformat(),
        },
    )
    if av.status_code != 200 or not (av.json().get("slots") or []):
        findings.fail("Sem slots livres para happy path")
        return None
    starts = datetime.fromisoformat(av.json()["slots"][0])
    key = f"qa-exp-{uuid.uuid4().hex[:12]}"
    r = client.post(
        "/api/v1/scheduling/appointments/",
        json={
            "customer_id": CUSTOMER_ID,
            "professional_id": PROFESSIONAL_ID,
            "service_id": SERVICE_CORTE_ID,
            "starts_at": starts.isoformat(),
            "idempotency_key": key,
            "explicit_confirmation": True,
            "source": "admin",
        },
    )
    if r.status_code != 201:
        findings.fail(f"Create appointment -> {r.status_code}: {r.text[:400]}")
        return None
    appt = r.json()
    appt_id = appt["id"]
    findings.ok(f"Create appointment pending id={appt_id}")

    # replay idempotency
    r2 = client.post(
        "/api/v1/scheduling/appointments/",
        json={
            "customer_id": CUSTOMER_ID,
            "professional_id": PROFESSIONAL_ID,
            "service_id": SERVICE_CORTE_ID,
            "starts_at": starts.isoformat(),
            "idempotency_key": key,
            "explicit_confirmation": True,
            "source": "admin",
        },
    )
    if r2.status_code == 201 and r2.json().get("id") == appt_id:
        findings.ok("Idempotency replay retorna mesmo appointment")
    else:
        findings.bug(f"Idempotency replay -> {r2.status_code} id={r2.json().get('id')}")

    # overlap
    r3 = client.post(
        "/api/v1/scheduling/appointments/",
        json={
            "customer_id": CUSTOMER_ID,
            "professional_id": PROFESSIONAL_ID,
            "service_id": SERVICE_CORTE_ID,
            "starts_at": (starts + timedelta(minutes=10)).isoformat(),
            "idempotency_key": f"qa-ov-{uuid.uuid4().hex[:8]}",
            "source": "admin",
        },
    )
    if r3.status_code in (400, 409, 422):
        findings.ok(f"Overlap rejeitado -> {r3.status_code}")
    else:
        findings.bug(f"Overlap aceito -> {r3.status_code} (esperado erro)")

    # FSM
    for action, expect in (
        ("confirm", "confirmed"),
        ("check-in", "checked_in"),
        ("start", "in_progress"),
        ("complete", "completed"),
    ):
        rr = client.post(f"/api/v1/scheduling/appointments/{appt_id}/{action}/", json={})
        if rr.status_code != 200:
            findings.fail(f"FSM {action} -> {rr.status_code}: {rr.text[:200]}")
            return appt_id
        if rr.json().get("status") != expect:
            findings.bug(f"FSM {action}: status={rr.json().get('status')} esperado={expect}")
        else:
            findings.ok(f"FSM {action} -> {expect}")

    # financial after complete
    rf = client.get(f"/api/v1/scheduling/appointments/{appt_id}/financial/")
    if rf.status_code == 200:
        findings.ok(
            f"Financial após complete: price={rf.json().get('service_price_cents')}"
        )
    else:
        findings.bug(f"Financial após complete -> {rf.status_code}")

    # commission entries
    rc = client.get("/api/v1/scheduling/commission-entries/")
    if rc.status_code == 200 and rc.json().get("count", 0) >= 1:
        findings.ok(f"Commission entries count={rc.json().get('count')}")
    elif rc.status_code == 200:
        findings.note("Commission entries vazio (regra seed pode não ter batido)")
    else:
        findings.fail(f"Commission entries -> {rc.status_code}")

    return appt_id


def check_availability(client: httpx.Client, findings: Findings) -> None:
    day = _next_weekday_slot().date().isoformat()
    r = client.get(
        "/api/v1/scheduling/availability",
        params={
            "professional_id": PROFESSIONAL_ID,
            "service_id": SERVICE_CORTE_ID,
            "day": day,
        },
    )
    if r.status_code != 200:
        findings.fail(f"Availability -> {r.status_code}: {r.text[:200]}")
        return
    slots = r.json().get("slots") or []
    findings.ok(f"Availability {day}: {len(slots)} slots")
    if len(slots) == 0:
        findings.note("Nenhum slot — verificar business_hours seed / conflitos")


def check_lists_and_trailing(client: httpx.Client, findings: Findings) -> None:
    endpoints = [
        "/api/v1/scheduling/professionals/",
        "/api/v1/scheduling/services/",
        "/api/v1/scheduling/business-hours/",
        "/api/v1/scheduling/appointments/",
        "/api/v1/scheduling/commission-rules/",
    ]
    for ep in endpoints:
        r = client.get(ep)
        if r.status_code == 200:
            findings.ok(f"GET {ep} -> 200 count={r.json().get('count', 'n/a')}")
        else:
            findings.fail(f"GET {ep} -> {r.status_code}")

    # trailing slash: DRF geralmente redireciona
    r = client.get("/api/v1/scheduling/professionals", follow_redirects=False)
    if r.status_code in (301, 302):
        findings.note(f"GET professionals sem / -> {r.status_code} (redirect)")
    elif r.status_code == 200:
        findings.ok("GET professionals sem trailing slash aceito")
    else:
        findings.note(f"GET professionals sem / -> {r.status_code}")


def check_past_appointment(client: httpx.Client, findings: Findings) -> None:
    past = datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(days=1)
    r = client.post(
        "/api/v1/scheduling/appointments/",
        json={
            "customer_id": CUSTOMER_ID,
            "professional_id": PROFESSIONAL_ID,
            "service_id": SERVICE_CORTE_ID,
            "starts_at": past.isoformat(),
            "idempotency_key": f"qa-past-{uuid.uuid4().hex[:8]}",
            "source": "admin",
        },
    )
    if r.status_code in (400, 422):
        findings.ok(f"Agendamento no passado rejeitado -> {r.status_code}")
    else:
        findings.bug(f"Agendamento no passado aceito -> {r.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    findings = Findings()

    print(f"=== QA Exploratório Agendador @ {base} ===\n")
    with httpx.Client(base_url=base, timeout=30.0) as client:
        token = login(client, base, findings)
        if not token:
            _print_report(findings)
            return 1
        client.headers["Authorization"] = f"Bearer {token}"

        check_lists_and_trailing(client, findings)
        check_required_fields(client, findings)
        check_availability(client, findings)
        check_past_appointment(client, findings)
        check_happy_path(client, findings)

    _print_report(findings)
    return 1 if findings.failed or findings.bugs else 0


def _print_report(findings: Findings) -> None:
    print("\n--- RESULTADO ---")
    print(f"PASS: {len(findings.passed)}")
    for m in findings.passed:
        print(f"  [PASS] {m}".encode("utf-8", errors="replace").decode("utf-8"))
    print(f"FAIL: {len(findings.failed)}")
    for m in findings.failed:
        print(f"  [FAIL] {m}")
    print(f"BUGS: {len(findings.bugs)}")
    for m in findings.bugs:
        print(f"  [BUG]  {m}")
    print(f"NOTES: {len(findings.notes)}")
    for m in findings.notes:
        print(f"  [NOTE] {m}")

    report_path = __import__("pathlib").Path("Docs/QA_SCHEDULING_EXPLORATORY_LAST_RUN.md")
    fail_lines = [f"- {m}" for m in findings.failed] or ["- (nenhum)"]
    bug_lines = [f"- {m}" for m in findings.bugs] or ["- (nenhum)"]
    note_lines = [f"- {m}" for m in findings.notes] or ["- (nenhum)"]
    lines = [
        "# QA Exploratório — última execução",
        "",
        f"- PASS: {len(findings.passed)}",
        f"- FAIL: {len(findings.failed)}",
        f"- BUGS: {len(findings.bugs)}",
        f"- NOTES: {len(findings.notes)}",
        "",
        "## PASS",
        *[f"- {m}" for m in findings.passed],
        "",
        "## FAIL",
        *fail_lines,
        "",
        "## BUGS",
        *bug_lines,
        "",
        "## NOTES",
        *note_lines,
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRelatorio gravado em {report_path}")


if __name__ == "__main__":
    sys.exit(main())
