"""Badges de status DAS no Hub V4."""

from django.template import Context, Template

import pytest


@pytest.mark.parametrize(
    "status,tone,label",
    [
        ("DISPONIVEL", "success", "Disponível"),
        ("PROCESSANDO", "warning", "Processando"),
        ("VENCIDO", "danger", "Vencido"),
        ("PAGO", "success", "Pago"),
        ("CANCELADO", "neutral", "Cancelado"),
    ],
)
def test_guia_status_badge(status, tone, label):
    tpl = Template("{% load hub_v4_tags %}{% guia_status_badge status %}")
    html = tpl.render(Context({"status": status}))
    assert f"st-{tone}" in html
    assert label in html
