from __future__ import annotations

import json
import time
from pathlib import Path

from .base import SourceError, get_json

REACH = 30  # steam hands out depot ids right after their app's id, so the owner is a little below the depot
FORGET_AFTER = 7 * 24 * 3600  # a miss might be a lookup that failed, so ask again eventually


def _cache_path() -> Path:
    return Path.home() / ".cache/paws/depot_owners.json"


def _load() -> dict:
    try:
        data = json.loads(_cache_path().read_text())
    except (OSError, ValueError):
        return {"depots": {}, "names": {}}
    return data if isinstance(data, dict) else {"depots": {}, "names": {}}


def _save(cache: dict) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache))
    except OSError:
        pass


def _app(appid: int) -> dict:
    data = get_json(f"https://api.steamcmd.net/v1/info/{appid}")
    return data.get("data", {}).get(str(appid)) or {}


def _game_for(appid: int, app: dict) -> tuple[str, str] | None:
    """a dlc's depot belongs to the game it's for. redists and tools have depots too but aren't games to add"""
    common = app.get("common") or {}
    kind = str(common.get("type") or "").lower()
    if kind == "game":
        return str(appid), str(common.get("name") or "")
    parent = str(common.get("parent") or "")
    if kind == "dlc" and parent.isdigit():
        return parent, str((_app(int(parent)).get("common") or {}).get("name") or "")
    return None


def _search(depot: int) -> tuple[str, str] | None:
    for candidate in range(depot, max(depot - REACH, 0), -1):
        app = _app(candidate)
        if not app:
            continue
        row = (app.get("depots") or {}).get(str(depot))
        # depotfromapp means it's borrowed: the app lists it but the real owner is somewhere else
        if candidate == depot or (isinstance(row, dict) and "depotfromapp" not in row):
            return _game_for(candidate, app)
    return None


def owners(depots, limit: int = 40) -> dict[str, tuple[str, str]]:
    """depot id -> (game appid, game name) for each depot steam can place. a .manifest or a .key only ever names its
    depot, so this is how those get back to a game. answers are cached, `limit` caps fresh searches per call, and a
    failed lookup just isn't in the result"""
    cache = _load()
    known = cache.setdefault("depots", {})
    now = time.time()
    out = {}
    for depot in dict.fromkeys(str(d) for d in depots if str(d).isdigit()):
        hit = known.get(depot)
        if hit and (hit.get("appid") or now - hit.get("at", 0) < FORGET_AFTER):
            if hit.get("appid"):
                out[depot] = (hit["appid"], hit.get("name", ""))
            continue
        if limit <= 0:
            continue
        limit -= 1
        try:
            found = _search(int(depot))
        except (OSError, ValueError, SourceError):
            continue  # offline says nothing about the depot: don't remember it as a miss
        known[depot] = {"appid": found[0], "name": found[1]} if found else {"at": now}
        if found:
            out[depot] = found
    _save(cache)
    return out


def names(ids, limit: int = 40) -> dict[str, str]:
    """id -> name for config rows with no real label. an id can be an app or a depot, so try the store and then
    the depot search. ids with no answer aren't asked about again for a while"""
    from ..games.bulk import lookup_names

    cache = _load()
    known = cache.setdefault("names", {})
    now = time.time()
    fresh = [
        i for i in ids if i not in known or (not known[i].get("name") and now - known[i].get("at", 0) >= FORGET_AFTER)
    ][:limit]
    found = lookup_names(fresh) if fresh else {}
    for appid in fresh:
        if appid not in found:
            continue
        known[appid] = {"name": found[appid]}
    _save(cache)
    missing = [i for i in fresh if i not in found]
    placed = owners(missing, limit)
    cache = _load()
    known = cache.setdefault("names", {})
    answered = cache.get("depots", {})
    for appid in missing:
        name = placed.get(appid, ("", ""))[1]
        if name:
            known[appid] = {"name": name}
        elif appid in answered:  # the search really ran and found nothing. offline never gets this far
            known[appid] = {"at": now}
    _save(cache)
    return {i: known[i]["name"] for i in ids if known.get(i, {}).get("name")}
