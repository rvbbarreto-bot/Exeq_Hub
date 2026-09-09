"""Montagem da navegação lateral Hub V4 a partir de HUB_V4_SIDEBAR."""



from __future__ import annotations



from typing import Any



from django.conf import settings

from django.urls import NoReverseMatch, reverse





def _resolve_href(item: dict[str, Any]) -> str:

    url_name = item.get("url_name")

    if url_name:

        try:

            return reverse(url_name)

        except NoReverseMatch:

            pass

    return str(item.get("link") or "#")





def _match_score(path: str, href: str, *, exact: bool = False) -> int:

    if not href or href == "#":

        return -1

    target = href.rstrip("/") or "/"

    if exact:

        return len(target) if path == target else -1

    if path == target:

        return len(target)

    if path.startswith(f"{target}/"):

        return len(target)

    return -1





def _active_nav_key(

    request,

    items: list[dict[str, Any]],

    *,

    current_nav: str = "",

) -> str:

    if current_nav:

        return current_nav

    path = (request.path or "").rstrip("/") or "/"

    best_score = -1

    best_nav = ""

    for item in items:

        nav_key = str(item.get("nav") or "")

        href = _resolve_href(item)

        exact = nav_key == "dashboard"

        score = _match_score(path, href, exact=exact)

        if score > best_score:

            best_score = score

            best_nav = nav_key

    return best_nav





def build_sidebar_navigation(

    *,

    request,

    flags: dict[str, Any],

    current_nav: str = "",

) -> list[dict[str, Any]]:

    """Filtra itens por flag e marca grupo expandido se contém rota ativa."""

    config = getattr(settings, "HUB_V4_SIDEBAR", {})

    visible_items: list[dict[str, Any]] = []

    for group in config.get("navigation") or []:

        for item in group.get("items") or []:

            flag = item.get("flag")

            if flag and not flags.get(flag):

                continue

            visible_items.append(item)



    active_nav = _active_nav_key(request, visible_items, current_nav=current_nav)

    out: list[dict[str, Any]] = []



    for group in config.get("navigation") or []:

        items_out: list[dict[str, Any]] = []

        for item in group.get("items") or []:

            flag = item.get("flag")

            if flag and not flags.get(flag):

                continue

            nav_key = str(item.get("nav") or "")

            items_out.append(

                {

                    "title": item["title"],

                    "icon": item.get("icon") or "circle",

                    "href": _resolve_href(item),

                    "active": bool(active_nav and nav_key == active_nav),

                    "nav": nav_key,

                }

            )

        if not items_out:

            continue

        has_active = any(i["active"] for i in items_out)

        out.append(

            {

                "title": group.get("title") or "",

                "separator": bool(group.get("separator")),

                "collapsible": bool(group.get("collapsible", True)),

                "items": items_out,

                "expanded": has_active or not group.get("collapsible"),

            }

        )

    return out

