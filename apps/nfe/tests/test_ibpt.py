"""IBPT — vTotTrib aproximado."""

from __future__ import annotations

import json

import pytest

from apps.nfe.ibpt import _load_rates, compute_v_tot_trib_cents, ibpt_enabled


@pytest.fixture(autouse=True)
def _clear_ibpt_cache():
    _load_rates.cache_clear()
    yield
    _load_rates.cache_clear()


def test_ibpt_disabled_returns_zero(settings):
    settings.IBPT_ENABLED = False
    total = compute_v_tot_trib_cents(
        [{"ncm": "21069090", "total_cents": 10000}],
        emit_uf="SP",
    )
    assert total == 0


def test_ibpt_computes_from_json(settings, tmp_path):
    data_path = tmp_path / "ibpt.json"
    data_path.write_text(
        json.dumps([{"ncm": "21069090", "uf": "SP", "fed_pct": 10, "est_pct": 5, "mun_pct": 0}]),
        encoding="utf-8",
    )
    settings.IBPT_ENABLED = True
    settings.IBPT_DATA_PATH = str(data_path)
    _load_rates.cache_clear()
    total = compute_v_tot_trib_cents(
        [{"ncm": "21069090", "total_cents": 10000}],
        emit_uf="SP",
    )
    assert total == 1500


def test_ibpt_enabled_flag(settings):
    settings.IBPT_ENABLED = True
    assert ibpt_enabled() is True


def test_ibpt_sample_fixture_file(settings):
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[3]
        / "integrations/sefaz_nfe/tests/fixtures/ibpt_sp_sample.json"
    )
    assert fixture.is_file()
    settings.IBPT_ENABLED = True
    settings.IBPT_DATA_PATH = str(fixture)
    _load_rates.cache_clear()
    total = compute_v_tot_trib_cents(
        [{"ncm": "21069090", "total_cents": 10000}],
        emit_uf="SP",
    )
    assert total > 0
