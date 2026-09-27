from __future__ import annotations

import json
import time

from ..settings import cfg_dir

FILE = "update.json"


def _path():
    return cfg_dir() / FILE


def load() -> dict:
    try:
        data = json.loads(_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(**fields):
    data = {**load(), **fields}
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(data, indent=1))
    except OSError:
        pass


def fresh(interval_min: float, now: float | None = None) -> bool:
    at = load().get("checked_at")
    if not isinstance(at, (int, float)) or load().get("state") != "current":
        return False
    return (now if now is not None else time.time()) - at < interval_min * 60
