from __future__ import annotations

import re
from pathlib import Path

from .find import find_steam

_PATH_LINE = re.compile(r'"path"\s*"([^"]+)"')
_APPID = re.compile(r'"appid"\s*"(\d+)"')
_NAME = re.compile(r'"name"\s*"([^"]*)"')


def library_paths() -> list[Path]:
    """every steam library folder (external drives included) - one copy of libraryfolders.vdf
    at the main install lists them all, path and appid sizes both"""
    st = find_steam()
    if not st or not st.root:
        return []
    root = Path(st.root)
    out = [root]
    try:
        text = (root / "steamapps/libraryfolders.vdf").read_text(errors="replace")
    except OSError:
        return out
    for m in _PATH_LINE.finditer(text):
        p = Path(m.group(1))
        if p not in out:
            out.append(p)
    return out


def installed_appids() -> set[str]:
    """appids Steam has actual game files for, across every library folder. the closest local
    signal to "really owned and in your library" without needing Steam Web API auth"""
    return set(installed_games())


def installed_games() -> dict[str, str]:
    """appid -> name for everything actually installed, read straight from each library's own
    appmanifest_<id>.acf files. entirely local and offline - unlike the public store search,
    this also covers delisted/private/tool appids that never show up in a store search at all"""
    out: dict[str, str] = {}
    for folder in library_paths():
        for acf in (folder / "steamapps").glob("appmanifest_*.acf"):
            try:
                text = acf.read_text(errors="replace")
            except OSError:
                continue
            appid = _APPID.search(text)
            name = _NAME.search(text)
            if appid:
                out[appid.group(1)] = name.group(1) if name else appid.group(1)
    return out
