from __future__ import annotations

import shutil
import time
from pathlib import Path

BACKUP_ROOT = Path.home() / ".config/paws/backups"


def age(path: Path) -> str:
    seconds = int(max(0, time.time() - path.stat().st_mtime))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


MAX_BACKUPS = 20


def backup_file(path: Path) -> str | None:
    if not path.exists():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    newest = _newest(path.name)
    if newest is not None and _same_bytes(newest, path):
        return newest.name
    stamp = time.strftime("%Y%m%dT%H%M%S")
    name = f"{path.name}.{stamp}"
    n = 0
    while (BACKUP_ROOT / name).exists():
        n += 1
        name = f"{path.name}.{stamp}-{n}"
    shutil.copy2(path, BACKUP_ROOT / name)
    _prune(path.name)
    return name


def _versions(name):
    return sorted(p for p in BACKUP_ROOT.glob(f"{name}.*") if _is_stamp(p.name[len(name) + 1 :]))


def _is_stamp(tail):
    head = tail.split("-", 1)[0]
    return len(head) == 15 and head[8] == "T" and (head[:8] + head[9:]).isdigit()


def _newest(name):
    v = _versions(name) if BACKUP_ROOT.exists() else []
    return v[-1] if v else None


def _same_bytes(a, b):
    try:
        return a.stat().st_size == b.stat().st_size and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _prune(name):
    files = _versions(name)
    for old in files[: max(0, len(files) - MAX_BACKUPS)]:
        old.unlink(missing_ok=True)


def list_backups() -> list[Path]:
    if not BACKUP_ROOT.exists():
        return []
    return sorted(BACKUP_ROOT.iterdir(), reverse=True)


def restore(path: Path) -> bool:
    if not BACKUP_ROOT.exists():
        return False
    files = _versions(path.name)
    if not files:
        return False
    if path.exists():
        backup_file(path)
    shutil.copy2(files[-1], path)
    return True


def versions_of(name: str) -> list[Path]:
    if not BACKUP_ROOT.exists():
        return []
    return list(reversed(_versions(name)))


def restore_backup(backup_path: Path, target: Path) -> bool:
    if not backup_path.is_file():
        return False
    if target.exists():
        backup_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, target)
    return True


def snapshot_good(path: Path) -> str | None:
    """plain copy not copy2 so the mtime shows when paws last checked it was fine"""
    if not path.exists():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    good = BACKUP_ROOT / f"{path.name}.known-good"
    if not (good.exists() and _same_bytes(good, path)):
        shutil.copy(path, good)
    else:
        good.touch()
    return good.name


def known_good(name: str) -> Path | None:
    good = BACKUP_ROOT / f"{name}.known-good"
    return good if good.is_file() else None
