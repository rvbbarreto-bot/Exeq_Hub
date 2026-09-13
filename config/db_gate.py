"""Gate PO: SQLite só em pytest — runserver/migrate/shell sempre Postgres."""

from __future__ import annotations

import os
import sys


def env_truthy(key: str) -> bool:
    return (os.environ.get(key) or "").strip().lower() in {"1", "true", "yes"}


def running_pytest() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if "_pytest" in sys.modules or "pytest" in sys.modules:
        return True
    argv = [str(a or "") for a in sys.argv]
    for i, arg in enumerate(argv):
        low = arg.lower()
        if low in {"pytest", "py.test"} or low.endswith("pytest.exe"):
            return True
        if low == "-m" and i + 1 < len(argv) and argv[i + 1].lower() == "pytest":
            return True
    return False


def assert_sqlite_allowed() -> None:
    """
    EXEQ_TEST_SQLITE=1 só vale dentro de pytest.
    Lab/Hub (runserver, migrate, shell, celery) deve usar Postgres.
    """
    if not env_truthy("EXEQ_TEST_SQLITE"):
        return
    if running_pytest():
        return
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "EXEQ_TEST_SQLITE está ativo fora do pytest. "
        "Decisão PO: lab/Hub usa Postgres (docker compose up -d). "
        "Remova EXEQ_TEST_SQLITE do ambiente ou do .env antes de "
        "runserver/migrate/shell/celery. "
        "Pytest offline: EXEQ_TEST_SQLITE=1 python -m pytest …"
    )
