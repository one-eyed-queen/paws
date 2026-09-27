from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SlsInstall:
    kind: str = "native"
    lib_dir: Path | None = None
    sls_so: Path | None = None
    inject_so: Path | None = None
    config: Path | None = None
    cache: Path | None = None
    plugins: Path | None = None
    tools: Path | None = None
    desktop_used: bool = False
    managed_by: str | None = None
    path_wrappers: list[Path] = field(default_factory=list)
    installed_ts: float | None = None
