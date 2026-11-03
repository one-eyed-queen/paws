from __future__ import annotations

import json

from .. import config
from ..paths import paws_home
from .apply import apply_plan
from .plan import _in_library, plan_add

DEPOT_SECTIONS = ("ManifestIds", "DecryptionKeys", "AdditionalDepots")


def _skip_path():
    return paws_home() / "bg_add_skip.json"


def _skipped() -> set[str]:
    try:
        return {str(x) for x in json.loads(_skip_path().read_text())}
    except (OSError, ValueError, TypeError):
        return set()


def remember_removed(appid: str) -> None:
    """a removed game can leave depot rows behind, and those must not bring it back on the next start"""
    try:
        path = _skip_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(_skipped() | {str(appid)})))
    except OSError:
        pass


def missing_games() -> dict[str, str]:
    """appid -> name for games whose manifests or depot keys are in the config but which were never added. a game
    you already have in steam isn't missing: an AdditionalApps row would only override its owner id"""
    from ..sources.depots import owners

    data = config.parsed()
    depots = [str(d) for section in DEPOT_SECTIONS if isinstance(data.get(section), dict) for d in data[section]]
    listed = {str(a) for a in data.get("AdditionalApps") or []}
    skipped = _skipped()
    found = {}
    for appid, name in owners(depots).values():
        if appid not in listed and appid not in skipped and not _in_library(appid):
            found[appid] = name
    return found


def _plan(appid: str, name: str):
    from ..sources import from_store
    from ..sources.base import SourceError

    packages = []
    try:
        info = from_store(appid)
        name = name or info.name or ""
        packages = [str(p) for p in info.packages or []]
    except (OSError, ValueError, SourceError):
        pass
    return plan_add(appid, name=name, packages=packages)


def add_missing() -> list[str]:
    """the background half of add game. network first, and only then the one short batch of config writes, since
    config.batch is shared by the whole process and this runs on a worker thread"""
    from ..sources.store import free_ids

    plans = [_plan(appid, name) for appid, name in missing_games().items()]
    if not plans:
        return []
    free_ids([p.appid for p in plans])  # apply_plan reuses this answer instead of asking inside the batch
    added = []
    with config.batch():
        for plan in plans:
            # nudge=False: starting up must never kick off a download for every game it finds
            if apply_plan(plan, nudge=False).get("added"):
                added.append(plan.name or plan.appid)
    return added


def run() -> list[str]:
    """what paws does at every start: add games that are missing, then put names and order on the config rows"""
    from .. import settings
    from ..config.tidy import tidy, unnamed_ids
    from ..sources.depots import names

    if settings.missing_reason():
        return []
    added = add_missing()
    tidy(names(unnamed_ids()))
    return added
