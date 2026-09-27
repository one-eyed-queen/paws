from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from ..paths import HOME
from ..util import http

CACHE = HOME / ".cache/paws/appids.json"
LIMIT = 60


def _load():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _exists(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
    try:
        return bool(http.get_json(url, timeout=8).get(str(appid), {}).get("success"))
    except (OSError, ValueError):
        return None


def missing_on_store(ids):
    """app ids the steam store says don't exist. offline, rate limited or unsure ones are left out"""
    known = _load()
    todo = [i for i in ids if i not in known][:LIMIT]
    with ThreadPoolExecutor(max_workers=5) as pool:
        for appid, answer in zip(todo, pool.map(_exists, todo)):
            if answer is not None:
                known[appid] = answer
    if todo:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(known))
        except OSError:
            pass
    return [i for i in ids if known.get(i) is False]
