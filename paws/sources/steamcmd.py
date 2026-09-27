from __future__ import annotations

import re

from .base import GameInfo, SourceError, get_json

SLS_OUTPUT_ADDITIONAL = re.compile(r"AdditionalApps:\s*\n((?:\s+-.*\n?)+)", re.M)


SLS_OUTPUT_DLCTREE = re.compile(r"DlcData:\s*\n\s+(\d+):(.*?)(?=\n\S|\Z)", re.S)


SLS_OUTPUT_DLC = re.compile(r"\s+(\d+):\s*\"([^\"]*)\"")


def parse_sls_output(text: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    additional = []
    dlc_data = {}

    m = SLS_OUTPUT_ADDITIONAL.search(text or "")
    if m:
        for line in m.group(1).splitlines():
            ids = re.findall(r"(\d{3,})(?:#|\t|$)", line.strip().lstrip("- "))
            if ids:
                additional.append(ids[0])

    for tree in SLS_OUTPUT_DLCTREE.finditer(text or ""):
        parent = tree.group(1)
        block = {d: n for d, n in SLS_OUTPUT_DLC.findall(tree.group(2))}
        if block:
            dlc_data[parent] = block
    return additional, dlc_data


def from_steamcmd(appid: str) -> GameInfo:
    try:
        data = get_json(f"https://api.steamcmd.net/v1/info/{appid}")
    except (OSError, ValueError, SourceError) as e:
        raise SourceError(f"steamcmd lookup failed: {e}")
    app = data.get("data", {}).get(str(appid), {})
    if not app:
        raise SourceError(f"steamcmd: app {appid} not found")
    depots = {did: (d.get("name") or "Main") for did, d in app.get("depots", {}).items() if did.isdigit()}
    dlcs = [str(d) for d in app.get("extended", {}).get("listofdlc", [])]
    return GameInfo(
        appid=str(appid), name=app.get("common", {}).get("name", ""), depots=depots, dlcs=dlcs, source="steamcmd"
    )
