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


def _apps_block(text: str) -> str:
    """the inside of Software/Valve/Steam/apps in a localconfig.vdf, brace-matched so the rest of
    the file (playtime, cloud, controllers) doesn't get scanned for appids too"""
    i = text.find('"apps"')
    if i < 0:
        return ""
    start = text.find("{", i)
    if start < 0:
        return ""
    depth = 0
    for j in range(start, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : j]
    return ""


def owned_appids() -> set[str]:
    """appids Steam already keeps a library entry for: everything installed, plus every app the
    signed-in user's own localconfig has a block for.

    this is the line SLSsteam draws in its own config docs: AdditionalApps *injects* an app, which
    is the only way an unowned game shows up in the library at all - but for an app you already own
    or share it overrides the owner id and breaks downloads. so it has to be one or the other, and
    this tells us which."""
    out = installed_appids()
    root = find_steam()
    if not root or not root.root:
        return out
    for cfg in (Path(root.root) / "userdata").glob("*/config/localconfig.vdf"):
        try:
            text = cfg.read_text(errors="replace")
        except OSError:
            continue
        block = _apps_block(text)
        out |= {m.group(1) for m in re.finditer(r'^\s*"(\d{1,10})"\s*$', block, re.MULTILINE)}
    return out


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
