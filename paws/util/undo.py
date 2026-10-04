from __future__ import annotations

import json
from datetime import datetime, timezone

from ..paths import paws_home

JOURNAL = paws_home() / "undo.jsonl"


def log(kind: str, detail: dict):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "detail": detail,
    }
    with JOURNAL.open("a") as f:
        f.write(json.dumps(record) + "\n")


def history(limit: int = 100) -> list[dict]:
    if not JOURNAL.exists():
        return []
    recs = []
    for line in reversed(JOURNAL.read_text().splitlines()[-limit:]):
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return recs
