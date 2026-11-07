"""SLSsteam only unlocks a game. steam downloads it itself, and for that it needs each depot's key in its own
config.vdf and the depot's .manifest file in its depotcache. config.yaml keeps both lists (DecryptionKeys and
ManifestIds), but a reinstalled or moved steam starts with neither, and every game then sits at 0 B.

this puts them back: the keys from config.yaml, and the manifest files from paws' own copy (kept since this change,
see keep_manifests) or from anywhere they still sit in your home folder. steam has to be closed, it rewrites
config.vdf on exit and would throw the keys away again."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from ..paths import paws_home

NAME = re.compile(r"^(\d+)_(\d+)\.manifest$")
SKIP_DIRS = {".cache", ".local/share/Trash", "node_modules", ".git", "proc"}
SEARCH_DEPTH = 6


def store() -> Path:
    """paws' own copy of every manifest it has added, so moving steam again can't lose them"""
    return paws_home() / "depotcache"


def keep_manifests(files) -> None:
    folder = store()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for depot, manifest, source in files:
            target = folder / f"{depot}_{manifest}.manifest"
            if not target.exists() and Path(source).is_file():
                shutil.copy2(source, target)
    except OSError:
        pass


def wanted() -> tuple[dict[str, str], dict[str, str]]:
    """(depot -> key, depot -> manifest) from config.yaml"""
    from ..config import parsed

    data = parsed() or {}
    keys = {str(d): str(k).strip('"') for d, k in (data.get("DecryptionKeys") or {}).items() if k}
    manifests = {str(d): str(m) for d, m in (data.get("ManifestIds") or {}).items() if m}
    return keys, manifests


def _depotcache() -> Path | None:
    from .find import find_steam

    steam = find_steam()
    return Path(steam.depotcache) if steam and steam.depotcache else None


def missing() -> tuple[dict[str, str], dict[str, str]]:
    """what config.yaml has and steam doesn't: (keys, manifests)"""
    from . import vdf

    keys, manifests = wanted()
    have_keys = vdf.existing_depot_ids(list(keys)) if keys else set()
    cache = _depotcache()
    have = {p.name for p in cache.glob("*.manifest")} if cache and cache.is_dir() else set()
    return (
        {d: k for d, k in keys.items() if d not in have_keys},
        {d: m for d, m in manifests.items() if f"{d}_{m}.manifest" not in have},
    )


def find_files(manifests: dict[str, str]) -> dict[str, Path]:
    """depot -> a copy of the manifest file it needs: paws' own store first, then a walk through the home folder"""
    wanted_names = {f"{d}_{m}.manifest": d for d, m in manifests.items()}
    found: dict[str, Path] = {}
    for f in store().glob("*.manifest") if store().is_dir() else ():
        if f.name in wanted_names:
            found[wanted_names[f.name]] = f
    if len(found) == len(wanted_names):
        return found
    for name, path in _home_index().items():
        depot = wanted_names.get(name)
        if depot and depot not in found and path.is_file():
            found[depot] = path
    return found


_index: dict = {}
INDEX_FOR = 600.0


def _home_index() -> dict[str, Path]:
    """every .manifest under the home folder. walking it takes seconds, so it's done at most every 10 minutes"""
    import time

    if _index.get("at", 0) > time.monotonic() - INDEX_FOR:
        return _index["files"]
    files_found: dict[str, Path] = {}
    home = Path.home()
    for root, dirs, files in os.walk(home):
        depth = len(Path(root).relative_to(home).parts)
        rel = str(Path(root).relative_to(home))
        dirs[:] = [d for d in dirs if depth < SEARCH_DEPTH and f"{rel}/{d}".lstrip("./") not in SKIP_DIRS and d not in SKIP_DIRS]
        for name in files:
            if NAME.match(name):
                files_found.setdefault(name, Path(root) / name)
    _index.update(at=time.monotonic(), files=files_found)
    return files_found


def restore() -> dict:
    """puts the missing keys and manifests back. returns what it did and what it couldn't find"""
    from . import is_running, vdf

    if is_running():
        return {"error": "steam is running"}
    keys, manifests = missing()
    result = {"keys": 0, "manifests": 0, "not_found": []}
    if keys:
        done = vdf.inject_depot_keys(keys)
        if done.get("error"):
            result["error"] = done["error"]
        else:
            result["keys"] = len(keys)
    if manifests:
        cache = _depotcache()
        files = find_files(manifests)
        if cache is not None and files:
            cache.mkdir(parents=True, exist_ok=True)
            for depot, source in files.items():
                target = cache / source.name
                if not target.exists():
                    shutil.copy2(source, target)
                    result["manifests"] += 1
            keep_manifests([(d, manifests[d], p) for d, p in files.items()])
        result["not_found"] = sorted(set(manifests) - set(files))
    return result
