from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import settings
from .config import heal
from .util import backup

ORDER = ("nvim", "nano")
FALLBACKS = ("vim", "vi")


def find_editor() -> list[str] | None:
    for chosen in (os.environ.get("PAWS_EDITOR"), _setting()):
        if chosen:
            argv = shlex.split(chosen)
            if argv and shutil.which(argv[0]):
                return argv
    for name in ORDER:
        if shutil.which(name):
            return [name]
    for env in ("VISUAL", "EDITOR"):
        argv = shlex.split(os.environ.get(env, ""))
        if argv and shutil.which(argv[0]):
            return argv
    for name in FALLBACKS:
        if shutil.which(name):
            return [name]
    return None


def _setting():
    try:
        value = str(settings.get_setting("editor") or "")
    except Exception:
        return ""
    return "" if value in ("", "auto") else value


def editor_name(argv: list[str] | None = None) -> str:
    argv = argv or find_editor()
    return Path(argv[0]).name if argv else "none"


def yaml_problem(text: str) -> str | None:
    found = heal.yaml_problem(text)
    if found:
        line, reason = found
        return f"line {line}: {reason}" if line else reason
    data = yaml.safe_load(text)
    if data is not None and not isinstance(data, dict):
        return "the file should be a list of `Key: value` settings"
    return None


def section_line(path: Path, section: str) -> int | None:
    try:
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.startswith(f"{section}:"):
                return i
    except OSError:
        pass
    return None


@dataclass
class Edited:
    ran: bool
    changed: bool = False
    problem: str | None = None
    backup: str | None = None
    editor: str = ""
    error: str = ""


def _run(command):
    subprocess.run(command)


def open_in_editor(path: Path, line: int | None = None, suspend=None, run=None) -> Edited:
    """opens any file in nvim/nano and reports whether it changed. doesn't know or care what's inside it: config.yaml
    checks that separately in edit(), a plugin's .lua is just handed back as-is"""
    run = run or _run
    argv = find_editor()
    if argv is None:
        return Edited(False, error="no editor found: install neovim or nano (or set the `editor` setting)")
    bak = backup.backup_file(path)
    before = path.read_text() if path.exists() else ""
    command = [*argv, *([f"+{line}"] if line else []), str(path)]
    try:
        with suspend() if suspend is not None else nullcontext():
            run(command)
    except Exception as e:
        return Edited(False, backup=bak, editor=Path(argv[0]).name, error=f"couldn't run {Path(argv[0]).name}: {e}")
    after = path.read_text() if path.exists() else ""
    return Edited(True, changed=after != before, backup=bak, editor=Path(argv[0]).name)


def edit(path: Path, line: int | None = None, suspend=None, run=None) -> Edited:
    result = open_in_editor(path, line, suspend, run)
    if not result.ran:
        return result
    after = path.read_text() if path.exists() else ""
    result.problem = yaml_problem(after)
    return result


def put_back(path: Path, backup_name: str | None) -> bool:
    if not backup_name:
        return False
    return backup.restore_backup(backup.BACKUP_ROOT / backup_name, path)
