from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..util.backup import backup_file
from .io import raw_lines, write
from .seed import ensure_config
from .where import find_config


def set_scalar(key: str, value: str, backup: bool = True) -> bool:
    path = ensure_config()
    if backup:
        backup_file(path)
    lines = raw_lines(path)
    pat = re.compile(rf"^{re.escape(key)}:[ \t]*(.*?)(\s+#.*)?$")
    for i, l in enumerate(lines):
        m = pat.match(l)
        if m:
            lines[i] = f"{key}: {value}{m.group(2) or ''}"
            write(path, "\n".join(lines) + "\n")
            return True
    if not (lines and lines[-1].strip() == ""):
        lines.append("")
    lines.append(f"{key}: {value}")
    write(path, "\n".join(lines) + "\n")
    return True


def get_scalar(key: str) -> str | None:
    for l in raw_lines():
        m = re.match(rf"^\s*{re.escape(key)}:\s*(.*)$", l)
        if m:
            return m.group(1).strip()
    return None


def parsed(path: Path | None = None) -> dict:
    p = path or find_config()
    if p and p.exists():
        try:
            data = yaml.safe_load(p.read_text()) or {}
            if isinstance(data, dict):
                return data
        except yaml.YAMLError:
            pass
    return {}


def get_list(section: str) -> list[str]:
    d = parsed()
    v = d.get(section)
    if isinstance(v, list):
        return [str(x) for x in v]
    return []
