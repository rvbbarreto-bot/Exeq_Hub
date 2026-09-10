"""CSOSN → grupo XML ICMS na NF-e."""

from __future__ import annotations

import pytest

from apps.nfe.csosn import map_csosn_to_xml_group
from integrations.sefaz_nfe.tests.test_nfe_proc import _SNAP
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml


@pytest.mark.parametrize(
    "csosn,expected_group",
    [
        ("102", "ICMSSN102"),
        ("103", "ICMSSN102"),
        ("400", "ICMSSN400"),
        ("500", "ICMSSN500"),
        ("900", "ICMSSN900"),
        ("101", "ICMSSN101"),
        ("201", "ICMSSN201"),
    ],
)
def test_map_csosn_to_xml_group(csosn, expected_group):
    assert map_csosn_to_xml_group(csosn) == expected_group


@pytest.mark.parametrize("csosn,expected_group", [("400", "ICMSSN400"), ("103", "ICMSSN102")])
def test_build_nfe_xml_emits_correct_icms_group(csosn, expected_group):
    snap = dict(_SNAP)
    item = dict(snap["items"][0])
    item["taxes"] = {
        "icms": {"regime": "sn", "csosn": csosn, "xml_group": map_csosn_to_xml_group(csosn)},
        "pis": {"cst": "49"},
        "cofins": {"cst": "49"},
    }
    snap["items"] = [item]
    xml = build_nfe_xml(snapshot=snap).decode("utf-8")
    assert f"<{expected_group}>" in xml
    assert f"<CSOSN>{csosn.zfill(3)}</CSOSN>" in xml
