from __future__ import annotations

import json
import re

from ... import settings
from ...util import backup, fs, undo
from ..model import Problem
from ._shared import stamp, move_aside, safe_read


def check_settings() -> list[Problem]:
    f = settings.file_path()
    text = safe_read(f)
    if text is None:
        return []
    try:
        ok = isinstance(json.loads(text), dict)
    except ValueError:
        ok = False
    if ok:
        return []

    def fix() -> str:
        aside = move_aside(f)
        settings.save(dict(settings.DEFAULTS))
        return f"settings reset to defaults (the old file is {aside.name})"

    return [
        Problem(
            "paws.settings-broken",
            "paws' settings.json is broken",
            "paws falls back to defaults every time, so your choices don't stick",
            "move it aside and write fresh defaults",
            fix,
        )
    ]


def check_journal() -> list[Problem]:
    f = undo.JOURNAL
    text = safe_read(f)
    if text is None:
        return []
    bad = []
    for i, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except ValueError:
            bad.append(i)
    if not bad:
        return []

    def fix() -> str:
        backup.backup_file(f)
        keep = [l for i, l in enumerate(text.splitlines()) if i not in set(bad)]
        f.write_text("\n".join(keep) + ("\n" if keep else ""))
        return f"dropped {len(bad)} unreadable line(s)"

    return [
        Problem(
            "paws.journal-broken",
            f"{len(bad)} unreadable line(s) in the undo journal",
            "removing a game uses this journal to take out exactly what was added; bad lines are skipped",
            "drop those lines (the rest is kept)",
            fix,
        )
    ]


def check_tickets() -> list[Problem]:
    from ...sls import tickets

    d = tickets.cache_dir()
    if d is None or not fs.is_dir(d):
        return []
    bad = [
        f
        for f in d.glob("*.yaml")
        if re.search(r"(ticket|encryptedTicket)_\d+\.yaml$", f.name) and tickets.load_ticket_file(f) is None
    ]
    if not bad:
        return []

    def fix() -> str:
        quarantine = d / "broken"
        quarantine.mkdir(exist_ok=True)
        for f in bad:
            f.rename(quarantine / f"{f.name}.{stamp()}")
        return f"moved {len(bad)} to {quarantine}"

    return [
        Problem(
            "tickets.corrupt",
            f"{len(bad)} ticket file(s) can't be read",
            ", ".join(f.name for f in bad[:3]),
            "move them into a `broken` folder next to the cache (make new ones with Activation)",
            fix,
        )
    ]
