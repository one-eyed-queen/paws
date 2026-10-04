from __future__ import annotations

import json
import re
import time
from datetime import datetime

from ..util import pkgmgr
from .model import SlsInstall
from .release import github_releases

_TAG_RE = re.compile(r"\d{14}")


def _package_version(so):
    if so is None:
        return None
    owner = pkgmgr.owner_of(so)
    return str(owner) if owner else None


def installed_version(sls: SlsInstall | None) -> str | None:
    if sls is not None and sls.kind == "windows":
        return "windows port (under construction)"
    if sls is None or sls.lib_dir is None:
        return None
    if sls.managed_by:
        pv = _package_version(sls.sls_so)
        return f"{pv} ({sls.managed_by})" if pv else f"{sls.managed_by} package"
    info = sls.lib_dir / "paws.info.json"
    if info.exists():
        try:
            data = json.loads(info.read_text())
            return data.get("tag") or data.get("source_desc")
        except Exception:
            pass
    if sls.installed_ts:
        return f"installed {datetime.fromtimestamp(sls.installed_ts).date().isoformat()}"
    return "unknown"


def installed_tag(sls: SlsInstall | None) -> str | None:
    m = _TAG_RE.search(installed_version(sls) or "")
    return m.group(0) if m else None


def update_available(sls: SlsInstall | None, latest: str | None) -> bool | None:
    have = installed_tag(sls)
    if not have or not latest or not _TAG_RE.fullmatch(latest):
        return None
    return have < latest


_LATEST_CACHE: dict[str, tuple[float, str | None]] = {}


_LATEST_TTL = 600.0


def fetch_latest_github_tag() -> str | None:
    hit = _LATEST_CACHE.get("latest")
    if hit and time.time() - hit[0] < _LATEST_TTL:
        return hit[1]
    try:
        rels = github_releases(1, timeout=6)
        tag = rels[0].tag if rels else None
    except Exception:
        tag = None
    _LATEST_CACHE["latest"] = (time.time(), tag)
    return tag
