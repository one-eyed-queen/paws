from __future__ import annotations

import re
import time
from pathlib import Path

from ..util import http
from .schema import ordered_keys

GITHUB_TEMPLATE_URL = "https://raw.githubusercontent.com/AceSLS/SLSsteam/main/res/config.yaml"
_KEY_RE = re.compile(r"^([A-Za-z]\w*):", re.MULTILINE)
_TTL = 6 * 3600.0

_cache: dict[str, tuple[float, tuple[str, ...] | None]] = {}


def keys_in(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_KEY_RE.findall(text)))


def fetch_github_text(timeout=8.0):
    try:
        return http.get_text(GITHUB_TEMPLATE_URL, timeout=timeout)
    except (OSError, ValueError):
        return None


def fetch_github_keys(timeout: float = 6.0) -> tuple[str, ...] | None:
    hit = _cache.get("github")
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    text = fetch_github_text(timeout)
    keys = keys_in(text) if text is not None else None
    _cache["github"] = (time.time(), keys)
    return keys


def installed_template_keys(lib_dir: Path | None) -> tuple[str, ...] | None:
    if lib_dir is None:
        return None
    template = lib_dir / "res" / "config.yaml"
    if not template.is_file():
        return None
    try:
        return keys_in(template.read_text(errors="replace"))
    except OSError:
        return None


KNOWN_VALID = frozenset({"AdditionalDepots", "AdditionalPackages", "DecryptionKeys", "CloudProxies", "InventoryItems"})


def diff(upstream_keys: tuple[str, ...]) -> tuple[list[str], list[str]]:
    bundled = ordered_keys()
    bundled_set, upstream_set = set(bundled), set(upstream_keys)
    added = [k for k in upstream_keys if k not in bundled_set]
    removed = [k for k in bundled if k not in upstream_set and k not in KNOWN_VALID]
    return added, removed
