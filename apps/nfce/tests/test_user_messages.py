"""Mensagens amigáveis NFC-e."""

from apps.nfce.user_messages import format_nfce_gate_errors


def test_format_nfce_gate_csc_friendly():
    failed = [{"id": "csc", "ok": False, "label": "CSC não cadastrado", "must": True}]
    msg = format_nfce_gate_errors(failed)
    assert "contador" in msg.lower()
    assert "CSC" in msg
    assert "CSC não cadastrado" not in msg
    assert "[" not in msg


def test_format_nfce_gate_csc_priority_over_series():
    failed = [
        {"id": "csc", "ok": False, "label": "CSC não cadastrado", "must": True},
        {"id": "series", "ok": False, "label": "Série 1/1 auto-criada (stub)", "must": True},
    ]
    msg = format_nfce_gate_errors(failed)
    assert "contador" in msg.lower()
    assert "stub" not in msg.lower()
