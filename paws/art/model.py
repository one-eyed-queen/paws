from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_PH = re.compile(r"\$\{?c(\d+)\}?")


_STCOL = re.compile("(?i)^\\s*\\(?\\s*set_colors\\s*[:=]?\\s*([0-9,\\s]+)\\s*\\)?\\s*$")


_COLEQ = re.compile("(?i)^\\s*colors\\s*=\\s*\\(([^)]*)\\)\\s*$")


_TITLE = re.compile("(?i)^\\s*#+\\s*title\\s*[:=]\\s*(.+?)\\s*$")


_PALHDR = re.compile("(?i)^\\s*palette\\s*[:=]\\s*(.+?)\\s*$")


PH_RE = _PH


@dataclass
class Art:
    name: str
    lines: list[str] = field(default_factory=list)
    slots: list[int] = field(default_factory=list)
    palette: dict[int, str | None] = field(default_factory=dict)
    path: Path | None = None
    title: str = ""
    source: str = "bundled"
    nsfw: bool = False

    @property
    def colored(self) -> bool:
        return any(_PH.search(l) for l in self.lines)


def clean_art_name(value):
    return re.sub(r"\s+", "", value)
