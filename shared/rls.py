from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from django.conf import settings
from django.db import connection


def _subject_role() -> str:
    return getattr(settings, "RLS_SUBJECT_ROLE", "exeq_app")


def set_rls(*, tenant_id: str | None = None, bypass: bool = False) -> None:
    """Define contexto RLS da conexão atual (session-level)."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        if bypass:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', false)")
            cursor.execute("SELECT set_config('app.tenant_id', '', false)")
            return
        # Superuser local (Docker) ignora RLS; assume role sujeito a FORCE RLS.
        cursor.execute(f"SET ROLE {_subject_role()}")
        cursor.execute("SELECT set_config('app.bypass_rls', 'off', false)")
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, false)",
            [str(tenant_id or "")],
        )


def clear_rls() -> None:
    set_rls(bypass=True)


@contextmanager
def tenant_rls(tenant_id: str) -> Iterator[None]:
    set_rls(tenant_id=str(tenant_id), bypass=False)
    try:
        yield
    finally:
        clear_rls()


@contextmanager
def bypass_rls() -> Iterator[None]:
    set_rls(bypass=True)
    try:
        yield
    finally:
        clear_rls()
