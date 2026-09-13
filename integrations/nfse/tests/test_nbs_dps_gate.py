"""Testes do portão cNBS no DPS."""

import pytest
from django.test import override_settings

from integrations.nfse.nbs_dps_gate import (
    MODE_HOMOLOG,
    MODE_OFF,
    MODE_ON,
    cnbs_dps_gate_mode,
    include_cnbs_in_dps,
)


@pytest.mark.parametrize(
    ("mode", "tp_amb", "expected"),
    [
        (MODE_OFF, 1, False),
        (MODE_OFF, 2, False),
        (MODE_HOMOLOG, 1, False),
        (MODE_HOMOLOG, 2, True),
        (MODE_ON, 1, True),
        (MODE_ON, 2, True),
    ],
)
def test_include_cnbs_in_dps_by_mode(mode, tp_amb, expected):
    with override_settings(NFSE_DPS_CNBS_MODE=mode):
        assert include_cnbs_in_dps(tp_amb=tp_amb) is expected


def test_cnbs_dps_gate_mode_unknown_falls_back_to_off():
    with override_settings(NFSE_DPS_CNBS_MODE="invalid"):
        assert cnbs_dps_gate_mode() == MODE_OFF
