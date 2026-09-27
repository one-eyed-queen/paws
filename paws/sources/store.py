from __future__ import annotations

import re
import urllib.request

from .base import GameInfo, SourceError, get_json

BLACKLIST = [
    "soundtrack",
    "ost",
    "original soundtrack",
    "artbook",
    "graphic novel",
    "demo",
    "server",
    "dedicated server",
    "tool",
    "sdk",
    "3d print model",
]


def search_store(term: str, *, cc: str = "us", l: str = "en") -> list[GameInfo]:
    url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(term)}&cc={cc}&l={l}"
    try:
        data = get_json(url)
    except (OSError, ValueError, SourceError) as e:
        raise SourceError(f"store search failed: {e}")
    out = []
    for it in data.get("items", []):
        if not it.get("id"):
            continue
        name = it.get("name", "")
        if any(re.search(rf"\b{re.escape(k)}\b", name.lower()) for k in BLACKLIST):
            continue
        out.append(
            GameInfo(
                appid=str(it["id"]),
                name=name,
                price=it.get("price", "") or "",
                source="store",
                header_image=it.get("tiny_image", "") or "",
            )
        )
    return out


def from_store(appid: str) -> GameInfo:
    try:
        data = get_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=en")
    except (OSError, ValueError, SourceError) as e:
        raise SourceError(f"store lookup failed: {e}")
    app = data.get(appid or str(appid), {})
    if not app.get("success"):
        raise SourceError(f"store: app {appid} not found")
    info = app.get("data", {})
    price = info.get("price_overview", {})
    screens = [s.get("path_full", "") for s in info.get("screenshots", [])]
    return GameInfo(
        appid=str(appid),
        name=info.get("name", ""),
        price=price.get("final_formatted", ""),
        free=bool(info.get("is_free")),
        packages=[str(p) for p in info.get("packages", [])],
        dlcs=[str(d) for d in info.get("dlc", [])],
        source="store",
        short_description=info.get("short_description", ""),
        about=info.get("detailed_description", ""),
        developers=info.get("developers", []) or info.get("publishers", []),
        header_image=info.get("header_image", "") or "",
        screenshots=screens,
    )
