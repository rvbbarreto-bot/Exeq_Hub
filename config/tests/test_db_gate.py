"""Gate PO — SQLite bloqueado fora de pytest."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from config.db_gate import assert_sqlite_allowed, env_truthy, running_pytest


def test_env_truthy():
    os.environ["GATE_TEST"] = "1"
    try:
        assert env_truthy("GATE_TEST") is True
        os.environ["GATE_TEST"] = "yes"
        assert env_truthy("GATE_TEST") is True
        os.environ["GATE_TEST"] = "0"
        assert env_truthy("GATE_TEST") is False
    finally:
        os.environ.pop("GATE_TEST", None)


def test_running_pytest_when_current_test_set():
    os.environ["PYTEST_CURRENT_TEST"] = "test_db_gate.py::test_x (call)"
    try:
        assert running_pytest() is True
    finally:
        os.environ.pop("PYTEST_CURRENT_TEST", None)


def test_assert_sqlite_allowed_no_flag():
    os.environ.pop("EXEQ_TEST_SQLITE", None)
    assert_sqlite_allowed()


def test_assert_sqlite_allowed_under_pytest():
    os.environ["EXEQ_TEST_SQLITE"] = "1"
    os.environ["PYTEST_CURRENT_TEST"] = "config/tests/test_db_gate.py::test (call)"
    try:
        assert_sqlite_allowed()
    finally:
        os.environ.pop("EXEQ_TEST_SQLITE", None)
        os.environ.pop("PYTEST_CURRENT_TEST", None)


def test_assert_sqlite_blocked_outside_pytest(monkeypatch):
    from django.core.exceptions import ImproperlyConfigured

    monkeypatch.setenv("EXEQ_TEST_SQLITE", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr("config.db_gate.running_pytest", lambda: False)
    with pytest.raises(ImproperlyConfigured, match="EXEQ_TEST_SQLITE"):
        assert_sqlite_allowed()


def test_manage_check_fails_with_sqlite_env_outside_pytest():
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    env = os.environ.copy()
    env["EXEQ_TEST_SQLITE"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)
    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "EXEQ_TEST_SQLITE" in (result.stderr + result.stdout)
