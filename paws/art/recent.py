from __future__ import annotations

import json
import math
import random
from functools import lru_cache

from .dirs import user_cfg_dir
from .library import nsfw_allowed, library

RECENT_FILE = "art_recent.json"

RECENT_LIMIT = 10
WIDE_LIMIT = 20
HISTORY_KEEP = 100


def freshness_window(pool_size: int, wide: bool = False) -> int:
    if pool_size <= 1:
        return 0
    want = WIDE_LIMIT if wide else RECENT_LIMIT
    return min(want, pool_size - 1)


def recent_names() -> list[str]:
    try:
        data = json.loads((user_cfg_dir() / RECENT_FILE).read_text())
        if isinstance(data, list):
            return [str(x) for x in data]
    except (OSError, ValueError):
        pass
    return []


def note_pick(name: str):
    if not name:
        return
    recent = [n for n in recent_names() if n != name]
    recent.insert(0, name)
    recent = recent[:HISTORY_KEEP]
    try:
        p = user_cfg_dir() / RECENT_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(recent))
    except OSError:
        pass


SAME_PICTURE = 0.65
_GRID = 24
_MIN_SIDE = 12


@lru_cache(maxsize=256)
def _signature(lines):
    from .fit import is_blank, trim

    rows = trim(list(lines))
    if len(rows) < _MIN_SIDE:
        return None
    h, w = len(rows), max(len(r) for r in rows)
    if w < _MIN_SIDE:
        return None
    ink = [
        [
            bin(ord(ch) - 0x2800).count("1") / 8 if "\u2800" <= ch <= "\u28ff" else (0.0 if is_blank(ch) else 1.0)
            for ch in row.ljust(w)
        ]
        for row in rows
    ]
    v = []
    for gy in range(_GRID):
        y0 = gy * h // _GRID
        y1 = max(y0 + 1, (gy + 1) * h // _GRID)
        for gx in range(_GRID):
            x0 = gx * w // _GRID
            x1 = max(x0 + 1, (gx + 1) * w // _GRID)
            cells = [ink[y][x] for y in range(y0, min(y1, h)) for x in range(x0, min(x1, w))]
            v.append(sum(cells) / len(cells))
    mean = sum(v) / len(v)
    v = [x - mean for x in v]
    norm = math.sqrt(sum(x * x for x in v))
    return tuple(x / norm for x in v) if norm else None


def alike(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    sa, sb = _signature(a), _signature(b)
    if sa is None or sb is None:
        return False
    return sum(x * y for x, y in zip(sa, sb)) >= SAME_PICTURE


_canon_memo: dict = {}


def _canonical(pool):
    keys = {name: tuple(line.rstrip() for line in pool[name].lines) for name in pool}
    memo_key = tuple(sorted((n, hash(k)) for n, k in keys.items()))
    if _canon_memo.get("key") == memo_key:
        return dict(_canon_memo["value"])
    value = _canonical_uncached(keys)
    _canon_memo["key"], _canon_memo["value"] = memo_key, value
    return dict(value)


def _canonical_uncached(keys):
    names = sorted(keys)
    parent = {n: n for n in names}

    def find(n: str) -> str:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a: str, b: str):
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            parent[hi] = lo

    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if keys[a] == keys[b] or alike(keys[a], keys[b]):
                union(a, b)

    return {n: find(n) for n in names}


def random_pick(
    tier: str | None = None,
    nsfw: bool | None = None,
    rng: random.Random | None = None,
    avoid: list[str] | None = None,
    remember: bool = True,
) -> str | None:
    rng = rng or random
    lib = library(nsfw=True)
    lib = {n: a for n, a in lib.items() if a.lines}
    if tier is None:
        tier = ("sfw", "both", "nsfw")[rng.randrange(3)]
    allow = nsfw_allowed(nsfw)
    if tier == "nsfw" and not allow:
        tier = "sfw"
    if tier == "nsfw":
        pool = {n: a for n, a in lib.items() if a.nsfw} or lib
    elif tier == "both":
        pool = {n: a for n, a in lib.items() if allow or not a.nsfw}
    else:
        pool = {n: a for n, a in lib.items() if not a.nsfw}
    if not pool:
        return None

    canon = _canonical(pool)
    pieces = sorted(set(canon.values()))
    if avoid is not None:
        skip = {canon.get(n, n) for n in avoid}
    else:
        seen = []
        for n in recent_names():
            c = canon.get(n)
            if c and c not in seen:
                seen.append(c)
        skip = set(seen[: freshness_window(len(pieces), wide=allow)])
    candidates = [n for n in pieces if n not in skip] or pieces
    chosen = candidates[rng.randrange(len(candidates))]
    if remember:
        note_pick(chosen)
    return chosen
