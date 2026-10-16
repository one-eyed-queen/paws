from __future__ import annotations

from pathlib import Path

__all__ = ["__version__"]


def _read_version() -> str:
    here = Path(__file__).resolve().parent
    for p in (here.parent / "version", here / "version", here / "_version.txt"):
        if p.exists():
            try:
                first = p.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
                if first:
                    return first
            except Exception:
                continue
    return "0.0.0"


__version__ = _read_version()
