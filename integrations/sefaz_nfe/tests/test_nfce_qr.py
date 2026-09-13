"""QR Code NFC-e v2 — hash online SP."""

from __future__ import annotations

import hashlib

from integrations.sefaz_nfe.nfce_supplement import (
    build_qr_code_url,
    qr_hash_online_v2,
)


def test_qr_hash_online_v2_nt_formula():
    key = "35260837229907000137650010000000011000000010"
    csc_id = "1"
    token = "HOMOLOGCSC"
    expected = hashlib.sha1(f"{key}|2|2|{csc_id}{token}".encode()).hexdigest().upper()
    assert qr_hash_online_v2(
        access_key=key,
        tp_amb="2",
        csc_id=csc_id,
        csc_token=token,
    ) == expected


def test_build_qr_code_url_homolog_sp():
    key = "35260837229907000137650010000000011000000010"
    url = build_qr_code_url(
        access_key=key,
        tp_amb="2",
        csc_id="1",
        csc_token="HOMOLOGCSC",
    )
    assert url.startswith(
        "https://www.homologacao.nfce.fazenda.sp.gov.br/"
        "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx?p="
    )
    parts = url.split("?p=")[1].split("|")
    assert parts[0] == key
    assert parts[1] == "2"
    assert parts[2] == "2"
    assert parts[3] == "1"
    assert len(parts[4]) == 40
