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


_FREE: dict[str, bool] = {}


def free_ids(appids) -> set[str]:
    """which of these the store gives away for free (free games, free dlc, free tools...). one bulk price lookup
    first: anything with a price isn't free. only the priceless ones (free, delisted, not out yet) get the full
    lookup, since delisted and unreleased apps have no price either. an answer the store can't give counts as not
    free, so an offline paws never refuses to add anything"""
    ids = [a for a in dict.fromkeys(str(x) for x in appids) if a.isdigit()]
    todo = [a for a in ids if a not in _FREE]
    for start in range(0, len(todo), 100):
        chunk = todo[start : start + 100]
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={','.join(chunk)}&filters=price_overview&cc=us"
            data = get_json(url)
        except (OSError, ValueError, SourceError):
            continue
        for appid in chunk:
            entry = data.get(appid) if isinstance(data, dict) else None
            if not isinstance(entry, dict) or not entry.get("success"):
                continue
            if isinstance(entry.get("data"), dict) and entry["data"].get("price_overview"):
                _FREE[appid] = False
                continue
            try:
                app = next(
                    iter(get_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us").values())
                )
            except (OSError, ValueError, SourceError, StopIteration):
                continue
            if app.get("success"):
                _FREE[appid] = bool(app.get("data", {}).get("is_free"))
    return {a for a in ids if _FREE.get(a)}


def _package(packageid: str) -> dict | None:
    """the store's details for a package, {} when the store doesn't sell it, None when it couldn't be asked"""
    try:
        data = get_json(f"https://store.steampowered.com/api/packagedetails?packageids={packageid}&cc=us")
    except (OSError, ValueError, SourceError):
        return None
    entry = next(iter(data.values()), {}) if isinstance(data, dict) else {}
    return entry.get("data", {}) if entry.get("success") else {}


def main_package(appid: str, info: dict) -> list[str]:
    """the one package AdditionalPackages should get: the plain "Buy <game>" option. appdetails' `packages` also
    lists other editions, commercial licenses and even other apps (Portal 2 lists The Final Hours, app 104600), and
    injecting those can loop steam on "loading user data". a package only counts once packagedetails shows the game
    in it. none found (free game, offline) means none written"""
    for group in info.get("package_groups", []):
        if group.get("name") != "default":
            continue
        for sub in group.get("subs", []):
            packageid = str(sub.get("packageid") or "")
            details = (_package(packageid) if packageid else None) or {}
            if "commercial license" in str(details.get("name", "")).lower():
                continue
            if str(appid) in {str(a.get("id")) for a in details.get("apps", [])}:
                return [packageid]
    return []


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
        packages=main_package(appid, info),
        dlcs=[str(d) for d in info.get("dlc", [])],
        source="store",
        short_description=info.get("short_description", ""),
        about=info.get("detailed_description", ""),
        developers=info.get("developers", []) or info.get("publishers", []),
        header_image=info.get("header_image", "") or HEADER_CDN.format(appid=appid),
        screenshots=screens,
    )
