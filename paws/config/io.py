from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from .where import find_config

_pending: dict[Path, str] | None = None


def raw_lines(path: Path | None = None) -> list[str]:
    p = path or find_config()
    if not p:
        return []
    if _pending is not None and p.resolve() in _pending:
        return _pending[p.resolve()].splitlines()
    if not p.exists():
        return []
    return p.read_text().splitlines()


@contextmanager
def batch():
    """gather every edit then write once, SLSsteam pops a notice on every write"""
    global _pending
    if _pending is not None:
        yield
        return
    _pending = {}
    try:
        yield
        todo, _pending = _pending, None
    except BaseException:
        _pending = None
        raise
    for path, text in todo.items():
        write_now(path, text)


def write(path, text):
    if _pending is not None:
        _pending[path.resolve()] = text
        return
    write_now(path, text)


def write_now(path, text):
    """temp file then rename so a crash can't leave half a config"""
    target = path.resolve()
    temporary_path = target.with_name(target.name + ".paws-tmp")
    write_lf(temporary_path, text)
    try:
        os.chmod(temporary_path, target.stat().st_mode & 0o7777)
    except OSError:
        pass
    _replace(temporary_path, target)


def write_lf(path, text):
    """windows would turn every \n into \r\n and write cp1252, SLSsteam's config wants plain utf-8 lines"""
    if os.name == "nt":
        path.write_text(text, encoding="utf-8", newline="\n")
    else:
        path.write_text(text)


def _replace(src, target, tries=10):
    """on windows the rename fails while anything else has the file open (steam, an antivirus scan): wait it out"""
    for attempt in range(tries):
        try:
            os.replace(src, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == tries - 1:
                raise
            time.sleep(0.2)
