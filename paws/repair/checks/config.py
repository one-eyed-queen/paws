from __future__ import annotations

import os
import stat
from pathlib import Path


from ...config import heal
from ...config.io import write_now
from ...config.seed import default_config_text, fill_missing, missing_keys
from ...config.where import find_config
from ...paths import default_config_dir
from ...util import backup
from ..model import Problem
from ._shared import move_aside, safe_read


def _parses_and_differs(candidate, broken):
    try:
        data = candidate.read_bytes()
    except OSError:
        return False
    return data != broken and heal.yaml_ok(data.decode(errors="replace"))


def _valid_backup_for(config_path):
    try:
        broken = config_path.read_bytes()
    except OSError:
        broken = b""
    good = backup.known_good(config_path.name)
    if good is not None and _parses_and_differs(good, broken):
        return good
    if not backup.BACKUP_ROOT.exists():
        return None
    for cand in reversed(backup._versions(config_path.name)):
        if _parses_and_differs(cand, broken):
            return cand
    return None


def check_config_missing() -> list[Problem]:
    if find_config() is not None:
        return []

    def fix() -> str:
        target = default_config_dir() / "config.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(default_config_text())
        return f"created {target}"

    return [
        Problem(
            "config.missing",
            "no config.yaml",
            "SLSsteam has nothing to read, so it does nothing (and complains).",
            "write a complete starter config with every key SLSsteam expects",
            fix,
        )
    ]


def check_config_broken(config_path: Path) -> list[Problem]:
    try:
        text = config_path.read_text(errors="replace")
    except OSError:
        return []
    found = heal.yaml_problem(text)
    if found is None:
        return []
    line, reason = found
    where = f"line {line}: " if line else ""
    healed = heal.heal(text)
    good = _valid_backup_for(config_path)

    if healed.ok and healed.fixed:
        lines = ", ".join(str(f.line) for f in healed.fixed[:8])

        def fix() -> str:
            backup.backup_file(config_path)
            write_now(config_path, healed.text)
            return f"repaired {len(healed.fixed)} line(s) ({lines}), everything else left alone; backup kept"

        note = "repair just these, keep the rest as you wrote it:\n     " + "\n     ".join(
            str(f) for f in healed.fixed[:8]
        )
        return [Problem("config.yaml-broken", "config.yaml isn't valid yaml", where + reason, note, fix, "error")]

    def restore() -> str:
        if good is not None:
            backup.backup_file(config_path)
            config_path.write_bytes(good.read_bytes())
            return f"restored {good.name}"
        aside = move_aside(config_path)
        config_path.write_text(default_config_text())
        return f"no good backup: started a fresh config (the broken one is {aside.name})"

    note = (
        f"couldn't repair it safely: put back the newest backup that parses ({good.name}). look at {where or 'the file'}"
        if good
        else "couldn't repair it safely and no good backup exists: move this file aside and start a fresh config"
    )
    return [Problem("config.yaml-broken", "config.yaml isn't valid yaml", where + reason, note, restore, "error")]


def check_config_values(config_path: Path, online: bool = False) -> list[Problem]:
    text = safe_read(config_path)
    if text is None or heal.yaml_problem(text) is not None:
        return []
    fixed_text, fixes, stuck = heal.check_values(text)
    out = []
    if fixes:

        def fix() -> str:
            backup.backup_file(config_path)
            write_now(config_path, fixed_text)
            return f"fixed {len(fixes)} value(s) (lines {', '.join(str(f.line) for f in fixes[:8])}); backup kept"

        out.append(
            Problem(
                "config.values-fixable",
                f"{len(fixes)} value(s) in config.yaml are written wrong",
                "; ".join(str(f) for f in fixes[:6]),
                "rewrite them the way SLSsteam reads them",
                fix,
                "error",
            )
        )
    if stuck:
        out.append(
            Problem(
                "config.values",
                f"{len(stuck)} value(s) in config.yaml don't fit their key",
                "; ".join(str(f) for f in stuck[:8]),
                "paws can't guess the right value: check those lines",
                None,
                "error",
            )
        )
    if online:
        from ...config.appids import missing_on_store

        ids = heal.app_ids_with_lines(text)
        gone = missing_on_store(list(ids))
        if gone:
            out.append(
                Problem(
                    "config.appids",
                    f"{len(gone)} app id(s) the steam store doesn't know",
                    "; ".join(f"line {ids[i]}: {i}" for i in gone[:8])
                    + " (unreleased, removed or hidden apps show up here too)",
                    "check the ids, paws leaves them in",
                    None,
                    "warn",
                )
            )
    return out


def check_config_keys(config_path: Path) -> list[Problem]:
    if not heal.yaml_ok(safe_read(config_path) or ""):
        return []
    missing = missing_keys(config_path)
    if not missing:
        return []
    head = ", ".join(missing[:4]) + ("..." if len(missing) > 4 else "")
    return [
        Problem(
            "config.keys-missing",
            f"{len(missing)} config key(s) missing",
            f"SLSsteam pops a warning on every reload for each one ({head})",
            "add them at their defaults; your values stay as they are",
            lambda: f"added {len(fill_missing(config_path))} key(s)",
        )
    ]


def find_duplicates(lines: list[str]) -> list[int]:
    dup = []
    section = None
    seen = set()
    for i, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            section = line.split(":", 1)[0]
            seen = set()
            continue
        key = line.strip()
        if section and key in seen:
            dup.append(i)
        else:
            seen.add(key)
    return dup


def check_config_dupes(config_path: Path) -> list[Problem]:
    text = safe_read(config_path)
    if text is None or not heal.yaml_ok(text):
        return []
    lines = text.splitlines()
    dup = find_duplicates(lines)
    if not dup:
        return []

    def fix() -> str:
        backup.backup_file(config_path)
        drop = set(dup)
        write_now(config_path, "\n".join(l for i, l in enumerate(lines) if i not in drop) + "\n")
        return f"removed {len(drop)} repeated line(s)"

    return [
        Problem(
            "config.duplicates",
            f"{len(dup)} repeated line(s) in config.yaml",
            "the same entry listed twice in one section: harmless but it grows and confuses removal",
            "remove the second copy of each",
            fix,
        )
    ]


def check_config_encoding(config_path: Path) -> list[Problem]:
    try:
        raw = config_path.read_bytes()
    except OSError:
        return []
    bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
    if not (bom or crlf):
        return []
    what = " and ".join(x for x, on in (("a byte-order mark", bom), ("windows (CRLF) line endings", crlf)) if on)

    def fix() -> str:
        backup.backup_file(config_path)
        data = raw.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
        config_path.write_bytes(data)
        return "cleaned the file"

    return [
        Problem(
            "config.encoding",
            "config.yaml has " + what,
            "usually from editing it on windows: SLSsteam's parser can trip on it",
            "strip the mark / convert to unix line endings",
            fix,
        )
    ]


def _chmod(path, mode):
    path.chmod(mode & 0o7777)
    return f"permissions now {oct(mode & 0o777)}"


def check_config_permissions(config_path: Path) -> list[Problem]:
    try:
        mode = config_path.stat().st_mode
    except OSError:
        return []
    problems = []
    if not os.access(config_path, os.W_OK):
        problems.append(
            Problem(
                "config.readonly",
                "config.yaml isn't writable by you",
                f"{config_path} (paws and SLSsteam's own tools can't save changes)",
                "give you write permission on it",
                lambda: _chmod(config_path, mode | stat.S_IWUSR),
            )
        )
    elif mode & stat.S_IWOTH:
        problems.append(
            Problem(
                "config.world-writable",
                "config.yaml is writable by everyone",
                "any user on this machine could change what SLSsteam loads",
                "remove group / other write permission",
                lambda: _chmod(config_path, mode & ~(stat.S_IWGRP | stat.S_IWOTH)),
            )
        )
    return problems
