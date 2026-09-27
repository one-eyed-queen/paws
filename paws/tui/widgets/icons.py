from __future__ import annotations

import json
import os
import shutil
import subprocess

from ...paths import DATA_DIR as _DATA_DIR

DATA_DIR = _DATA_DIR

ICONS = json.loads((DATA_DIR / "icons.json").read_text())["icons"]

PLAIN = {
    "home": "⌂",
    "status": "◉",
    "install": "↓",
    "add": "+",
    "remove": "−",
    "activation": "◆",
    "keys": "*",
    "sections": "≡",
    "restore": "↺",
    "alias": "$",
    "quit": "×",
    "go": "›",
    "back": "‹",
    "box": "▪",
    "art": "▨",
    "settings": "≣",
    "nsfw": "!",
    "terminal": ">",
    "banner": "▨",
    "games": "♦",
}

_MODE: str | None = None
_SAMPLE = ("f011", "e69b", "eb6b")


def _fonts_have_nerd_glyphs():
    fc = shutil.which("fc-list")
    if not fc:
        return False
    try:
        out = subprocess.run(
            [fc, f":charset={' '.join(_SAMPLE)}", "family"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


def reset():
    global _MODE
    _MODE = None


def mode() -> str:
    global _MODE
    if _MODE is not None:
        return _MODE
    if os.environ.get("PAWS_NO_ICONS") is not None:
        _MODE = "none"
        return _MODE
    choice = os.environ.get("PAWS_ICONS")
    if not choice:
        try:
            from ... import settings

            choice = str(settings.get_setting("icons"))
        except Exception:
            choice = "auto"
    if choice not in ("nerd", "plain", "none"):
        choice = "nerd" if _fonts_have_nerd_glyphs() else "plain"
    _MODE = choice
    return _MODE


def icon(name: str) -> str:
    m = mode()
    if m == "none":
        return ""
    if m == "plain":
        return PLAIN.get(name, "•")
    pair = ICONS.get(name, ["", ""])
    return pair[0] if pair[0] else pair[1]


ICONS_ENABLED = True
