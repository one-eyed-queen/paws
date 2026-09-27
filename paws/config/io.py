from __future__ import annotations

import os
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
    temporary_path.write_text(text)
    try:
        os.chmod(temporary_path, target.stat().st_mode & 0o7777)
    except OSError:
        pass
    os.replace(temporary_path, target)
