from __future__ import annotations

import re
from pathlib import Path

from ...paths import HOME
from ...util import backup, fs
from ..model import Problem
from ._shared import move_aside, safe_read

USER_APPS = HOME / ".local/share/applications"
STEAM_LAUNCHERS = ("steam.desktop", "steam-native.desktop")
_AUDIT_RE = re.compile(r'LD_AUDIT="?([^"\s]+)"?')


def audit_paths(text: str) -> list[str]:
    out = []
    for m in _AUDIT_RE.finditer(text):
        out += [x for x in m.group(1).split(":") if x]
    return out


def strip_ld_audit(text: str) -> str:
    return re.sub(r'env\s+LD_AUDIT="[^"]*"\s+', "", re.sub(r"env\s+LD_AUDIT=\S+\s+", "", text))


def check_launchers(apps: Path | None = None) -> list[Problem]:
    apps = apps or USER_APPS
    out = []
    for name in STEAM_LAUNCHERS:
        f = apps / name
        if not fs.is_file(f):
            continue
        text = safe_read(f)
        if text is None:
            continue
        if "Exec=" not in text:
            out.append(
                Problem(
                    f"launcher.empty:{name}",
                    f"{name} is broken (no Exec line)",
                    f"{f} hides the real Steam launcher, so Steam may not show in your menu",
                    "move it aside so the system's launcher shows again",
                    lambda f=f: f"moved to {move_aside(f).name}",
                )
            )
            continue
        gone = [x for x in audit_paths(text) if not fs.exists(x)]
        if gone:

            def fix(f=f, text=text) -> str:
                backup.backup_file(f)
                f.write_text(strip_ld_audit(text))
                return f"took SLSsteam out of {f.name}: steam starts normally again"

            out.append(
                Problem(
                    f"launcher.dangling:{name}",
                    f"{name} points at SLSsteam files that are gone",
                    f"missing: {', '.join(gone[:2])}. Steam won't start from this launcher",
                    "remove the SLSsteam injection from it (reinstall SLSsteam afterwards to put it back)",
                    fix,
                    "error",
                )
            )
    return out
