from __future__ import annotations

import re
import shutil
from pathlib import Path

from .find import find_steam


def cache_root() -> Path | None:
    st = find_steam()
    for d in (
        st.depotcache if st else None,
        Path.home() / ".steam/root/depotcache",
        Path.home() / ".steam/steam/depotcache",
    ):
        if d and d.exists():
            return Path(d)
    return None


def list_manifests(depot: int | None = None) -> list[tuple[int, int, Path]]:
    r = cache_root()
    out = []
    if not r:
        return out
    for f in r.glob("*.manifest"):
        m = re.match(r"(\d+)_(\d+)\.manifest$", f.name)
        if m:
            out.append((int(m.group(1)), int(m.group(2)), f))
    if depot is not None:
        out = [t for t in out if t[0] == depot]
    return sorted(out)


def install_manifests(files: list[tuple[int, int, Path]]) -> list[tuple[int, int]]:
    r = cache_root()
    if not r:
        raise FileNotFoundError("depotcache not found")
    added = []
    for depot, mid, src in files:
        dst = r / f"{depot}_{mid}.manifest"
        if not dst.exists():
            shutil.copy2(src, dst)
            added.append((depot, mid))
    return added


def remove_manifest(depot: int, mid: int) -> bool:
    r = cache_root()
    f = r / f"{depot}_{mid}.manifest" if r else None
    if f is not None and f.exists():
        f.unlink()
        return True
    return False


def remove_depot(depot: int) -> list[str]:
    r = cache_root()
    if not r:
        return []
    removed = []
    for f in r.glob(f"{depot}_*.manifest"):
        f.unlink(missing_ok=True)
        removed.append(f.name)
    return removed


def remove_all() -> list[str]:
    r = cache_root()
    if not r:
        return []
    removed = []
    for f in r.glob("*.manifest"):
        f.unlink(missing_ok=True)
        removed.append(f.name)
    return removed
