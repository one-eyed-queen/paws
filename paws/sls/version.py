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
        # report what can actually be seen: the HubCapTools build paws installed, if it recorded
        # one. don't claim a version we can't determine
        from ..windows import port

        seen = port.installed_version()
        if seen:
            return f"HubCapTools {seen}"
        return f"windows port (config only, {sls.config})" if sls.config else "windows port"
    if sls is None or sls.lib_dir is None:
        return None
    if sls.managed_by:
        pv = _package_version(sls.sls_so)
        return f"{pv} ({sls.managed_by})" if pv else f"{sls.managed_by} package"
    info = sls.lib_dir / "paws.info.json"
    if info.exists():
        try:
            data = json.loads(info.read_text())
        except Exception:
            data = {}
        # build_tag is the release this was installed from and is the only thing comparable to
        # github's tags. "tag" holds the asset filename (SLSsteam-Any-release.7z), which has no
        # digits to compare, so installs done by paws used to report "can't tell, private build?"
        # against the very release they came from.
        for key in ("build_tag", "tag"):
            value = str(data.get(key) or "")
            if _TAG_RE.fullmatch(value):
                return value
        return data.get("tag") or data.get("source_desc")
    if sls.installed_ts:
        return f"installed {datetime.fromtimestamp(sls.installed_ts).date().isoformat()}"
    return "unknown"


def installed_tag(sls: SlsInstall | None) -> str | None:
    m = _TAG_RE.search(installed_version(sls) or "")
    return m.group(0) if m else None


# "no", "yes", "unknown" or "not installed". the old code folded "can't tell" into "no", so a
# private build (which has no 14-digit github tag) always read as up to date, forever
NO = "no"
YES = "yes"
UNKNOWN = "unknown"
ABSENT = "not installed"


def update_state(sls: SlsInstall | None, latest: str | None) -> str:
    if sls is None:
        return ABSENT
    have = installed_tag(sls)
    if not latest:
        return UNKNOWN
    if not have:
        return UNKNOWN
    if not _TAG_RE.fullmatch(latest):
        return UNKNOWN
    return YES if have < latest else NO


def update_reason(sls: SlsInstall | None, latest: str | None) -> str:
    """why update_state came out the way it did, in words fit to show a person"""
    state = update_state(sls, latest)
    if state == ABSENT:
        return "SLSsteam isn't installed yet"
    if state == UNKNOWN:
        current = installed_version(sls) or "unknown"
        if not latest:
            return f"can't reach github to check, showing the installed one ({current})"
        if not _TAG_RE.fullmatch(latest or ""):
            return f"github's newest tag ({latest}) isn't a comparable build id"
        return f"installed {current} came from somewhere else (a private build?), so paws can't compare it to github's"
    if state == NO:
        return f"{installed_version(sls)} is the newest github has"
    return f"{installed_version(sls)} -> {latest}"


def update_available(sls: SlsInstall | None, latest: str | None) -> bool | None:
    state = update_state(sls, latest)
    if state == YES:
        return True
    if state == NO:
        return False
    return None


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
