from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from .. import config
from ..paths import paws_home
from .apply import apply_plan
from .plan import _in_library, plan_add

DEPOT_SECTIONS = ("ManifestIds", "DecryptionKeys", "AdditionalDepots")  # keyed by depot
APP_SECTIONS = ("AppIds", "AdditionalApps", "AppTokens", "DlcData")  # app ids, typed in by hand or left by older paws


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


def _ids(data, sections) -> list[str]:
    found = []
    for section in sections:
        value = data.get(section)
        if isinstance(value, (dict, list)):
            found += [str(x) for x in value]
    return found


def missing_games(progress=None) -> dict[str, str]:
    """appid -> name for games the config knows about (depot keys, manifests, or an id put in by hand) that never
    went through add game, which writes both AdditionalApps and AppIds. owners() turns a dlc or depot into its game.
    a game you already have in steam isn't missing: an AdditionalApps row would only override its owner id"""
    from ..sources.depots import owners

    data = config.parsed()
    from .download import packages_supported

    allowed = {str(a) for a in data.get("AppIds") or []}
    complete = allowed & {str(a) for a in data.get("AdditionalApps") or []}
    if packages_supported():  # or it got its license the other way: its own store package is in AdditionalPackages
        have = {str(p) for p in data.get("AdditionalPackages") or []}
        complete |= {a for a in allowed - complete if set(_store_packages(a)) & have}
    skipped = _skipped()
    found = {}
    for appid, name in owners(_ids(data, DEPOT_SECTIONS) + _ids(data, APP_SECTIONS), progress=progress).values():
        if appid not in complete and appid not in skipped and not _in_library(appid):
            found[appid] = name
    return found


_PACKAGES = None


def _store_packages(appid: str) -> list[str]:
    """the game's store package (see sources.store.main_package), remembered in ~/.cache/paws so the live fixer
    asks the store once per game, not on every config change. [] for none, or when the store can't be reached"""
    import json
    from pathlib import Path

    global _PACKAGES
    path = Path.home() / ".cache" / "paws" / "packages.json"
    if _PACKAGES is None:
        try:
            _PACKAGES = json.loads(path.read_text())
        except (OSError, ValueError):
            _PACKAGES = {}
    if appid not in _PACKAGES:
        from ..sources import from_store
        from ..sources.base import SourceError

        try:
            _PACKAGES[appid] = [str(p) for p in from_store(appid).packages or []]
        except (OSError, ValueError, SourceError):
            return []  # offline: ask again next time
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_PACKAGES))
        except OSError:
            pass
    return _PACKAGES[appid]


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


def add_missing(report=None) -> list[str]:
    """the background half of add game. network first, and only then the one short batch of config writes, since
    config.batch is shared by the whole process and this runs on a worker thread"""
    from ..sources.store import free_ids

    tell = report or (lambda *_: None)
    missing = missing_games(lambda done, total: tell("checking", done, total))
    if not missing:
        return []
    tell("adding", 0, len(missing))
    with ThreadPoolExecutor(max_workers=8) as pool:
        plans = list(pool.map(lambda item: _plan(*item), missing.items()))
    if not plans:
        return []
    free_ids([p.appid for p in plans])  # apply_plan reuses this answer instead of asking inside the batch
    added = []
    with config.batch():
        for number, plan in enumerate(plans, 1):
            tell("adding", number, len(plans), plan.name or plan.appid)
            # nudge=False: starting up must never kick off a download for every game it finds
            result = apply_plan(plan, nudge=False)
            if result.get("free"):  # refused for good, so it isn't looked up again every start
                remember_removed(plan.appid)
            elif result.get("added"):
                added.append(plan.name or plan.appid)
    return added


def name_rows() -> bool:
    """every row gets its game's full name. a failed lookup only leaves a row unnamed until the next try"""
    from ..config.tidy import tidy, unnamed_ids
    from ..sources.depots import names

    try:
        return tidy(names(unnamed_ids()))
    except Exception:
        return False


def run(report=None) -> list[str]:
    """what paws does at every start: add games that are missing, then put names and order on the config rows"""
    from .. import settings
    if not settings.get_setting("auto_add_games") or settings.missing_reason():
        return []
    from ..steam.sync import restore
    from .download import unblock

    added = add_missing(report)
    try:
        added += [f"{name} (download fixed)" for name in unblock()]
    except Exception:
        pass
    try:  # steam moved or reinstalled: its keys and manifests back from config.yaml and paws' copy
        put_back = restore()
        if put_back.get("error") == "steam is running":
            from ..steam.sync import missing

            keys, manifests = missing()
            if keys or manifests:
                added.append("steam is missing download keys: Status / Doctor > Repair fixes it (restarts steam)")
        elif put_back.get("keys") or put_back.get("manifests"):
            added.append(f"{put_back['keys']} key(s) and {put_back['manifests']} manifest(s) back in steam")
    except Exception:
        pass
    if report is not None:
        report("done", len(added), len(added))
    name_rows()
    return added
