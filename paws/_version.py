from __future__ import annotations

from pathlib import Path

__all__ = ["__version__"]


def _read_version() -> str:
    """the repo-root `version` file, so a bump of that one file moves `paws --version` with it.

    they used to be two files edited by hand - `version` on the release side and `__version__` on
    the package side - and the two drifted until the app was reporting 1.2.127 while the repo said
    2.0.127. reads only the first line, since `version` carries a channel name on the second.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "version", here / "version", here / "_version.txt"):
        try:
            if not candidate.is_file():
                continue
            first = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
        except OSError:
            continue
        if first:
            return first
    try:  # an installed copy has no repo-root file beside it: use what pip recorded when it was built from it
        from importlib.metadata import version

        return version("paws")
    except Exception:
        return "0.0.0"


__version__ = _read_version()
