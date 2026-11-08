from __future__ import annotations

import re
from pathlib import Path

from ...paths import HOME
from ...util import backup, fs
from ..model import Problem
from ._shared import move_aside, safe_read

USER_APPS = HOME / ".local/share/applications"
STEAM_LAUNCHERS = ("steam.desktop", "steam-native.desktop")


def audit_paths(text: str) -> list[str]:
    from ...sls.desktop import audit_values

    out = []
    for value in audit_values(text):
        out += [x for x in value.split(":") if x]
    return out


def strip_ld_audit(text: str) -> str:
    plain = re.sub('env\\s+"LD_AUDIT=(?:[^"\x00]|\x00.)*"\\s+', "", text.replace("\\\\", "\x00"))
    plain = re.sub(r'env\s+LD_AUDIT="[^"]*"\s+', "", re.sub(r"env\s+LD_AUDIT=[^\s\"]\S*\s+", "", plain))
    return plain.replace("\x00", "\\\\")


def check_launcher_quoting(apps: Path | None = None) -> list[Problem]:
    """launchers paws wrote before 4.4 quote LD_AUDIT="..." in the middle of the argument. the desktop entry spec
    doesn't allow that, and a launcher that keeps the quotes (xdg-open's steam:// handler did) starts steam
    without SLSsteam: unowned games get uninstalled at that start"""
    from ...sls.desktop import needs_requote, requote

    apps = apps or USER_APPS
    try:
        names = sorted(
            {*STEAM_LAUNCHERS, *(p.name for p in apps.glob("*.desktop") if p.name.lower().startswith("slssteam"))}
        )
    except OSError:
        return []
    broken = [apps / n for n in names if fs.is_file(apps / n) and needs_requote(safe_read(apps / n) or "")]
    if not broken:
        return []

    def fix() -> str:
        for f in broken:
            text = safe_read(f)
            if text is None or not needs_requote(text):
                continue
            backup.backup_file(f)
            f.write_text(requote(text))
        return f"rewrote the LD_AUDIT part of {', '.join(f.name for f in broken)}; backup kept"

    return [
        Problem(
            "launcher.quoting",
            f"{len(broken)} launcher(s) quote LD_AUDIT the way some launchers keep literally",
            f"{', '.join(f.name for f in broken)}: opened from a steam:// link, steam can start with the quotes in the "
            "path and without SLSsteam, and then it uninstalls the games you don't own",
            "write LD_AUDIT the desktop entry spec's way (same libraries, nothing else changes)",
            fix,
            "error",
        )
    ]


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


_AUDIT_FAIL = re.compile(r"ld\.so: object '([^']*)' cannot be loaded as audit interface: ([^;\n]*)")


def load_failure(log_text: str) -> str | None:
    """the loader's own words for dropping SLSsteam, from steam's console-linux.txt. ELFCLASS32 is steam's 64-bit
    helpers turning down the 32-bit library, which happens on every working start too, so it never counts"""
    found = None
    for path, why in _AUDIT_FAIL.findall(log_text):
        if "sls" in path.lower() and "ELFCLASS32" not in why:
            found = f"{why.strip()} ({path})"
    return found


def check_steam_without_sls() -> list[Problem]:
    """steam is open but SLSsteam isn't in it: unowned games ask to be bought, sit at 0 B, and steam uninstalls them
    at its next start. LD_AUDIT only takes when steam starts, so the only fix is starting it again the right way"""
    from ...sls.find import find_sls
    from ...steam import is_running
    from ...steam.find import find_steam
    from ...steam.launch import sls_injected

    try:
        if not is_running() or sls_injected() or find_sls() is None:
            return []
        steam = find_steam()
    except (ImportError, OSError):
        return []
    log = safe_read(Path(steam.root) / "logs" / "console-linux.txt") if steam and steam.root else None
    why = load_failure(log or "")
    return [
        Problem(
            "steam.sls-not-loaded",
            "steam is running without SLSsteam",
            "so games you don't own ask you to buy them, show 0 B, and steam uninstalls them when it starts"
            + (f". the loader turned SLSsteam down: {why}" if why else ""),
            "quit steam from its own menu and start it through paws or the SLSsteam launcher",
            None,
            "error",
        )
    ]
