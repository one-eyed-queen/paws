from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .features import FEATURES as _FEATURES
from .paths import paws_home

DEFAULTS: dict = {
    "nsfw": False,
    "disabled": [],
    "random_banner": True,
    "launch_cmd": "paws",
    "notifications": "auto",
    "notify_sound": False,
    "icons": "auto",
    "type": "riced",
    "terminal": "auto",
    "editor": "auto",
    "alias_shell": "",
    "auto_update": True,
    "update_interval_min": 5,
}


def cfg_dir() -> Path:
    return Path(os.environ.get("PAWS_CONFIG_DIR") or paws_home())


def file_path() -> Path:
    return cfg_dir() / "settings.json"


FEATURES = [f.key for f in _FEATURES if f.toggleable]
RICED_ONLY = {f.key for f in _FEATURES if f.riced_only}
NEEDS_SLS = {f.key for f in _FEATURES if f.needs_sls}
FEATURE_LABELS = {f.key: f.label for f in _FEATURES if f.toggleable}
FEATURE_DESCS = {f.key: f.desc for f in _FEATURES if f.toggleable}


TYPES = ("riced", "minimal")


def ui_type() -> str:
    value = os.environ.get("PAWS_TYPE") or str(get_setting("type"))
    if value not in TYPES:
        value = "riced"
    from . import riced

    return value if value == "minimal" or riced.installed() else "minimal"


def is_minimal() -> bool:
    return ui_type() == "minimal"


def _launch_cmd(value):
    v = str(value).strip() if value else ""
    return DEFAULTS["launch_cmd"] if v in ("", "nyah", "paws") else v


def load() -> dict:
    try:
        data = json.loads(file_path().read_text())
        if isinstance(data, dict):
            merged = {**DEFAULTS, **data}
            merged["launch_cmd"] = _launch_cmd(merged.get("launch_cmd"))
            return merged
    except (OSError, ValueError):
        pass
    return dict(DEFAULTS)


def save(data: dict):
    cfg_dir().mkdir(parents=True, exist_ok=True)
    merged = {**DEFAULTS, **data}
    file_path().write_text(json.dumps(merged, indent=2) + "\n")
    try:
        os.chmod(file_path(), 0o600)
    except OSError:
        pass
    return merged


def get_setting(key: str):
    return load().get(key, DEFAULTS.get(key))


def set_setting(key: str, value):
    data = load()
    data[key] = value
    save(data)


_present = (0.0, True)


def sls_present():
    """is there an SLSsteam or a HeadCrab on this machine. asked a lot while drawing, so it's remembered for a second"""
    global _present
    if os.environ.get("PAWS_SHOW_ALL"):
        return True
    if time.monotonic() - _present[0] > 1.0:
        from .sls import headcrab
        from .sls.find import find_sls

        _present = (time.monotonic(), find_sls() is not None or bool(headcrab.footprint()))
    return _present[1]


def is_disabled(feature: str) -> bool:
    if feature in RICED_ONLY and is_minimal():
        return True
    if feature in NEEDS_SLS and not sls_present():
        return True
    return feature in load().get("disabled", [])


def toggle_disabled(feature: str) -> bool:
    data = load()
    dis = list(data.get("disabled", []))
    if feature in dis:
        dis.remove(feature)
        now = False
    else:
        dis.append(feature)
        now = True
    data["disabled"] = sorted(dis)
    save(data)
    return now


def status_report() -> dict:
    data = load()
    return {
        "nsfw": bool(data.get("nsfw")),
        "random_banner": bool(data.get("random_banner", True)),
        "launch_cmd": _launch_cmd(data.get("launch_cmd")),
        "terminal": str(data.get("terminal") or "auto"),
        "icons": str(data.get("icons") or "auto"),
        "type": ui_type(),
        "notifications": str(data.get("notifications") or "auto"),
        "features": {f: not is_disabled(f) for f in FEATURES},
    }
