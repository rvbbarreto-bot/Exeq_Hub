"""Guardas de escopo piloto para views Hub Food."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.food.pilot_scope import HUB_SECTION_LABELS, hub_section_in_pilot


def render_section_unavailable(
    request: HttpRequest,
    section: str,
    *,
    role: str,
) -> HttpResponse:
    label = HUB_SECTION_LABELS.get(section, section)
    return render(
        request,
        "hub_v4/food/section_unavailable.html",
        {
            "nav": "food",
            "role_code": role,
            "food_section": section,
            "page_title": f"{label} — indisponível",
            "section_label": label,
        },
        status=404,
    )


def block_if_out_of_pilot(
    request: HttpRequest, section: str, *, role: str
) -> HttpResponse | None:
    if hub_section_in_pilot(section):
        return None
    return render_section_unavailable(request, section, role=role)
