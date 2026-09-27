from __future__ import annotations

import json
import os
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import git


def _looks_like_paws(p):
    return (p / "pyproject.toml").is_file() and (p / "paws" / "__init__.py").is_file()


def _from_direct_url():
    try:
        raw = metadata.distribution("paws").read_text("direct_url.json")
        url = json.loads(raw).get("url", "") if raw else ""
    except (metadata.PackageNotFoundError, ValueError, OSError):
        return None
    if url.startswith("file://"):
        return Path(unquote(urlparse(url).path))
    return None


def find_checkout() -> Path | None:
    candidates = [
        os.environ.get("PAWS_SOURCE"),
        _from_direct_url(),
        Path(__file__).resolve().parents[2],
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c).expanduser()
        if p.is_dir() and _looks_like_paws(p) and git.is_repo(p):
            return p
    return None
