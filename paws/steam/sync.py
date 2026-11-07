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


def _keys_file() -> Path:
    return store().parent / "depot-keys.json"


def stored_keys() -> dict[str, str]:
    import json

    try:
        return {str(d): str(k) for d, k in json.loads(_keys_file().read_text()).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def remember_keys(keys: dict) -> None:
    """depot keys kept by paws itself: the public build has no DecryptionKeys section, and steam forgets config.vdf
    when it's moved or reinstalled. this is what puts them back"""
    import json

    have = stored_keys()
    new = {str(d): str(k) for d, k in keys.items() if k and have.get(str(d)) != str(k)}
    if not new:
        return
    have.update(new)
    path = _keys_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(have, indent=1, sort_keys=True))
    tmp.chmod(0o600)
    tmp.replace(path)


def wanted() -> tuple[dict[str, str], dict[str, str]]:
    """(depot -> key, depot -> manifest): config.yaml's lists plus the keys paws keeps itself"""
    from ..config import parsed

    data = parsed() or {}
    keys = stored_keys() | {str(d): str(k).strip('"') for d, k in (data.get("DecryptionKeys") or {}).items() if k}
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
    still = {name: depot for name, depot in wanted_names.items() if depot not in found}
    if still:
        found.update(_from_archives(still))
    return found


ARCHIVES = re.compile(r"\.(zip|7z|rar)$", re.IGNORECASE)
ARCHIVE_LIMIT = 500 * 1024 * 1024  # game bundles with .lua/.manifest files are small, multi-GB ones are game files


def _archive_members(path: Path) -> list[str]:
    """names inside an archive, remembered by size and date so each one is only read once"""
    import json

    cache_file = Path.home() / ".cache" / "paws" / "archive-index.json"
    try:
        cache = json.loads(cache_file.read_text())
    except (OSError, ValueError):
        cache = {}
    stat = path.stat()
    stamp = f"{stat.st_size}:{stat.st_mtime_ns}"
    entry = cache.get(str(path))
    if entry and entry.get("stamp") == stamp:
        return entry["names"]
    from ..drop import _member_names

    names = [n for n in _member_names(path) if n.endswith(".manifest")]
    cache[str(path)] = {"stamp": stamp, "names": names}
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache))
    except OSError:
        pass
    return names


def _from_archives(still: dict[str, str]) -> dict[str, Path]:
    """the manifests that only exist inside a downloaded .zip/.7z/.rar: copied out into paws' own store"""
    import subprocess

    found: dict[str, Path] = {}
    folder = Path.home() / "Downloads"
    if not folder.is_dir():
        return found
    for archive in sorted(folder.rglob("*")):
        if not ARCHIVES.search(archive.name) or not archive.is_file() or archive.stat().st_size > ARCHIVE_LIMIT:
            continue
        try:
            members = _archive_members(archive)
        except OSError:
            continue
        for member in members:
            name = Path(member).name
            depot = still.get(name)
            if not depot or depot in found:
                continue
            target = store() / name
            try:
                store().mkdir(parents=True, exist_ok=True)
                data = subprocess.run(["bsdtar", "-xOf", str(archive), member], capture_output=True, timeout=120).stdout
                if not data:
                    data = subprocess.run(["7z", "e", "-so", str(archive), member], capture_output=True, timeout=120).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            if data:
                target.write_bytes(data)
                found[depot] = target
        if len(found) == len(still):
            break
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


def restore(restart_steam: bool = False) -> dict:
    """puts the missing keys and manifests back. returns what it did and what it couldn't find.
    restart_steam: close steam first (the way its own quit does, so it saves its config before we write), then start
    it again with SLSsteam. only ever done when the user asked for the fix, never by the background fixer"""
    from . import is_running, vdf

    if is_running():
        if not restart_steam:
            return {"error": "steam is running"}
        from .process import kill_steam

        kill_steam(timeout=30.0)
        if is_running():
            return {"error": "steam didn't close"}
        try:
            result = restore()
        finally:
            _start_steam()
        return result
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


def _start_steam() -> None:
    from ..sls.find import find_sls
    from .find import find_steam
    from .launch import launch

    try:
        launch(find_steam(), find_sls())
    except Exception:
        pass
