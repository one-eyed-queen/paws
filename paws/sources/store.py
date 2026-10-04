from __future__ import annotations

import re
import urllib.parse

from .base import GameInfo, SourceError, get_json

HEADER_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

BLACKLIST = [
    "soundtrack",
    "ost",
    "original soundtrack",
    "artbook",
    "graphic novel",
    "demo",
    "beta",
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
        appid = str(it["id"])
        out.append(
            GameInfo(
                appid=appid,
                name=name,
                price=it.get("price", "") or "",
                source="store",
                # storesearch only hands back a tiny (~80px) thumbnail; the full header is at this fixed CDN
                # path for every app, no extra request needed to get something that isn't blurry
                header_image=HEADER_CDN.format(appid=appid),
            )
        )
    return out


def from_store(appid: str) -> GameInfo:
    try:
        data = get_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=en")
    except (OSError, ValueError, SourceError) as e:
        raise SourceError(f"store lookup failed: {e}")
    # steam's own key isn't always the appid we asked for (it can point at a linked app, e.g. a beta branch);
    # a single-appid request is always exactly one entry, so take that instead of assuming the key
    app = next(iter(data.values()), {})
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
        header_image=info.get("header_image", "") or HEADER_CDN.format(appid=appid),
        screenshots=screens,
    )
