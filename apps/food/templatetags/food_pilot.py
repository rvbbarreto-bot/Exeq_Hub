from django import template
from django.urls import NoReverseMatch, reverse

from apps.food.pilot_scope import (
    HUB_SECTION_LABELS,
    HUB_SECTION_NAV_KEYS,
    HUB_SECTION_ORDER,
    HUB_SECTION_URL_NAMES,
    admin_model_in_pilot,
    hub_section_in_pilot,
)

register = template.Library()


@register.filter
def food_pilot_model_enabled(object_name: str) -> bool:
    return admin_model_in_pilot(object_name)


@register.filter
def food_pilot_section_enabled(section: str) -> bool:
    return hub_section_in_pilot(section)


def _hub_nav_items(active_section: str | None = None, *, sidebar: bool = False):
    items = []
    for section in HUB_SECTION_ORDER:
        if not hub_section_in_pilot(section):
            continue
        try:
            url = reverse(HUB_SECTION_URL_NAMES[section])
        except NoReverseMatch:
            url = ""
        items.append(
            {
                "section": section,
                "label": HUB_SECTION_LABELS[section],
                "url": url,
                "active": section == active_section,
                "nav_key": HUB_SECTION_NAV_KEYS[section],
                "sidebar": sidebar,
            }
        )
    return {"items": items}


@register.inclusion_tag("hub_v4/food/_subnav_items.html")
def food_hub_subnav(active_section: str = "orders"):
    return _hub_nav_items(active_section)


@register.inclusion_tag("hub_v4/food/_sidebar_food_nav.html")
def food_hub_sidebar(active_nav: str = "food"):
    ctx = _hub_nav_items(sidebar=True)
    for item in ctx["items"]:
        item["active"] = item["nav_key"] == active_nav
    return ctx
