from __future__ import annotations

import re
from pathlib import Path

from ..paths import default_config_dir
from ..util.backup import backup_file
from .io import raw_lines, write
from .schema import SECTIONS, ordered_keys
from .where import find_config


def default_config_text() -> str:
    lines = ["# SLSsteam config (created by paws)", ""]
    for name in ordered_keys():
        lines += _default_block(name)
    return "\n".join(lines) + "\n"


def _default_block(name):
    metadata = SECTIONS["sections"][name]
    out = [f"# {metadata['desc']}"]
    if name == "IdleStatus":
        out += ["IdleStatus:", "  AppId: 0", '  Title: ""']
    elif name in SECTIONS.get("scalar_defaults", {}):
        value = SECTIONS["scalar_defaults"][name]
        out.append(f"{name}: {value}" if value != "" else f'{name}: ""')
    else:
        out.append(f"{name}:")
    out.append("")
    return out


def missing_keys(path: Path | None = None) -> list[str]:
    lines = raw_lines(path)
    present = {m.group(1) for l in lines if (m := re.match(r"^([A-Za-z]\w*):", l))}
    return [k for k in ordered_keys() if k not in present]


def fill_missing(path: Path | None = None) -> list[str]:
    path = path or ensure_config()
    missing = missing_keys(path)
    if not missing:
        return []
    backup_file(path)
    lines = raw_lines(path)
    if lines and lines[-1].strip():
        lines.append("")
    lines.append("# --- added by paws: keys SLSsteam expects ---")
    for name in missing:
        lines += _default_block(name)
    write(path, "\n".join(lines).rstrip("\n") + "\n")
    return missing


def ensure_config() -> Path:
    c = find_config()
    if c is None:
        c = default_config_dir() / "config.yaml"
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text(default_config_text())
    return c
