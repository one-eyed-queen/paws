from __future__ import annotations

import subprocess
from pathlib import Path

from ..paths import HOME
from .find import INJECT_NAMES, LIB_NAMES

_LAUNCHERS = {
    "steam.desktop": "Exec=steam %U",
    "steam-native.desktop": "Exec=steam-native %U",
}


def audit_targets(lib_dir: Path) -> list[Path]:
    """the libraries to put in LD_AUDIT, in the order the loader needs them, using the names that
    are actually on disk.

    this used to be a hardcoded f"{lib_dir}/library-inject.so:{lib_dir}/SLSsteam.so", which is only
    correct for the portable .7z. the arch package installs the same two files as
    libSLS-library-inject.so and libSLSsteam.so, so installing it produced a launcher pointing at
    two paths that do not exist - steam still started, with "cannot be preloaded: ignored" on every
    launch, and nothing was injected at all. so the names are looked up instead of assumed.

    empty files are skipped too: upstream's .7z currently ships a 0-byte bin/library-inject.so, and
    naming it in LD_AUDIT only earns a loader warning per launch.
    """
    found: list[Path] = []
    for names in (INJECT_NAMES, LIB_NAMES):
        for name in names:
            candidate = lib_dir / name
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    found.append(candidate)
                    break
            except OSError:
                continue
    return found


def write_launcher(sls_dir: Path) -> list[Path]:
    """point the steam launchers at this install. returns the libraries it wired in."""
    targets = audit_targets(sls_dir)
    if not targets:
        return []
    apps = HOME / ".local/share/applications"
    apps.mkdir(parents=True, exist_ok=True)
    audit = f'LD_AUDIT="{":".join(str(p) for p in targets)}"'
    wrote = False
    for name, fallback in _LAUNCHERS.items():
        sys_desktop = Path("/usr/share/applications") / name
        if not sys_desktop.exists():
            if name != "steam.desktop":
                continue
            content = f"[Desktop Entry]\nName=Steam\nComment=SLSsteam (paws)\n{fallback}\nIcon=steam\nTerminal=false\nType=Application\nCategories=Game;\nMimeType=x-scheme-handler/steam;\n"
        else:
            content = sys_desktop.read_text()
            if "Exec=" not in content:
                continue
        lines = []
        for line in content.splitlines():
            if line.startswith("Exec=") and "LD_AUDIT" not in line:
                line = f"Exec=env {audit} {line[len('Exec=') :]}"
            lines.append(line)
        (apps / name).write_text("\n".join(lines) + "\n")
        wrote = True
    if wrote:
        try:
            subprocess.run(["update-desktop-database", str(apps)], capture_output=True)
        except Exception:
            pass
    return targets


def strip_ld_audit(text: str) -> str:
    """remove the injection paws added, leaving the launcher otherwise as it was.

    uninstall used to delete ~/.local/share/applications/steam.desktop outright. when the system
    has its own copy that works out the same by accident, but a steam.desktop the user had edited
    was destroyed, and "uninstall slssteam" should not cost you your steam launcher.
    """
    out = []
    for line in text.splitlines():
        if "LD_AUDIT=" in line and line.startswith("Exec="):
            head, _, rest = line.partition("LD_AUDIT=")
            _, _, tail = rest.partition('"')
            tail = tail.lstrip(":").lstrip()
            out.append(f"{head}{tail}" if tail else head.rstrip())
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def sls_launchers(apps: Path | None = None) -> list[Path]:
    """desktop entries that exist only to launch steam with SLSsteam injected."""
    apps = apps or HOME / ".local/share/applications"
    out = []
    try:
        entries = sorted(apps.glob("*.desktop"))
    except OSError:
        return out
    for f in entries:
        if not f.name.lower().startswith("slssteam"):
            continue
        try:
            text = f.read_text()
        except OSError:
            continue
        if "LD_AUDIT" in text and "SLS" in text:
            out.append(f)
    return out


def launcher_targets(apps: Path | None = None) -> list[tuple[Path, list[str]]]:
    """every launcher's LD_AUDIT, as (launcher, paths). used to tell whether a launch still works
    after the install it points at has gone."""
    apps = apps or HOME / ".local/share/applications"
    out: list[tuple[Path, list[str]]] = []
    try:
        launchers = sorted(apps.glob("*.desktop"))
    except OSError:
        return out
    for f in launchers:
        try:
            text = f.read_text()
        except OSError:
            continue
        if "LD_AUDIT" not in text:
            continue
        # a launcher has one Exec per desktop action, and steam.desktop has a dozen. report the
        # distinct injection once per launcher instead of repeating it for every action.
        seen: set[str] = set()
        for chunk in text.split("LD_AUDIT=")[1:]:
            value = chunk.split('"')[1] if '"' in chunk else ""
            if value and value not in seen:
                seen.add(value)
                out.append((f, value.split(":")))
    return out
