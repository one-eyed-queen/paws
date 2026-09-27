from __future__ import annotations

import json
import re

from .dirs import PALETTES_FILE
from .model import clean_art_name

DEFAULT_PALETTE: dict[int, str | None] = {
    0: None,
    1: "red",
    2: "green",
    3: "yellow",
    4: "blue",
    5: "magenta",
    6: "cyan",
    7: "white",
    8: "bright_black",
    9: "bright_red",
    10: "bright_green",
    11: "bright_yellow",
    12: "bright_blue",
    13: "bright_magenta",
    14: "bright_cyan",
    15: "bright_white",
}


def palette_token(value):
    if isinstance(value, int):
        if value <= 0:
            return None
        return f"color({value})"
    if isinstance(value, str):
        v = clean_art_name(value)
        if not v or v.lower() in {"default", "none", "reset", "inherit"}:
            return None
        if re.fullmatch(r"[#a-fA-F0-9]{7}", v):
            return v
        if re.fullmatch(r"[a-zA-Z][\w]*(?:\([^)]*\))?", v):
            return v
    return None


def _load_palettes_json():
    if not PALETTES_FILE.exists():
        return {}
    try:
        data = json.loads(PALETTES_FILE.read_text()).get("palettes", {})
        return {name: {int(k): v for k, v in entries.items()} for name, entries in data.items()}
    except (OSError, ValueError, TypeError):
        return {}


def resolve_palette(
    slots,
    in_file,
    named,
    sidecar,
):
    pal = dict(DEFAULT_PALETTE)
    for s in slots:
        pal.setdefault(s, f"color({s})" if s else None)
    if named:
        palettes = _load_palettes_json()
        pal.update(palettes.get(named, {}))
    if sidecar:
        pal.update(sidecar)
    if in_file:
        pal.update(in_file)
    return pal


def parse_entry(value):
    parts = value.replace(":", " ", 1).split(None, 1)
    try:
        index = int(parts[0])
    except (ValueError, IndexError):
        return -1, None
    if len(parts) == 1:
        return -1, None
    raw = parts[1].strip().strip(",\"'")
    if raw.isdigit():
        return index, int(raw)
    return index, raw


def parse_palette_header(text):
    v = text.strip()
    if v.startswith("("):
        inner = v.strip("()")
        overrides = {}
        for part in re.split(r"[,;]", inner):
            index, color = parse_entry(part)
            if index >= 0:
                overrides[index] = color if color is not None else None
        return overrides, None
    return {}, v or None
