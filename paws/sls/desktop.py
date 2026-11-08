from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..paths import HOME
from .find import INJECT_NAMES, LIB_NAMES

_LAUNCHERS = {
    "steam.desktop": "Exec=steam %U",
    "steam-native.desktop": "Exec=steam-native %U",
}

# a separate entry that only ever launches steam with SLSsteam injected. packages used to drop one
# in the app menu; with only steam.desktop rewritten there is no "SLSsteam" app to click any more.
SLS_ENTRY = "SLSsteam.desktop"

# the three ways an Exec line carries it: the whole argument quoted (the spec's way), the old mid-argument quote
# paws used to write, and bare. matched with the file's own \\ escape already undone into _BS
_BS = "\x00"
_AUDIT_ARG = re.compile('"LD_AUDIT=((?:[^"\x00]|\x00.)*)"|LD_AUDIT="([^"]*)"|LD_AUDIT=([^\\s"]+)')
_RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")


def _plain(text: str) -> str:
    return text.replace("\\\\", _BS)


def _escaped(text: str) -> str:
    return text.replace(_BS, "\\\\")


def audit_arg(targets) -> str:
    """LD_AUDIT=<libs> as one Exec argument. the desktop entry spec only lets a quote wrap a whole argument, and
    some launchers hand LD_AUDIT="..." (a quote in the middle) to steam with the quotes still in it. xdg-open's
    steam:// handler did: SLSsteam didn't load, and steam deleted the unowned games at start"""
    arg = "LD_AUDIT=" + ":".join(str(p) for p in targets)
    if not any(c in _RESERVED for c in arg):
        return arg
    quoted = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return '"' + quoted.replace("\\", "\\\\") + '"'


def audit_values(text: str) -> list[str]:
    """every LD_AUDIT value in a launcher's Exec lines, however it's quoted"""
    out = []
    for whole, old, bare in _AUDIT_ARG.findall(_plain(text)):
        value = re.sub("\x00(.)", r"\1", whole) if whole else (old or bare).replace(_BS, "\\")
        if value:
            out.append(value)
    return out


def requote(text: str) -> str:
    """the old LD_AUDIT="..." Exec lines rewritten the spec's way, everything else left as it was"""
    lines = []
    for line in text.splitlines():
        if line.startswith("Exec="):
            line = re.sub(r'LD_AUDIT="([^"]*)"', lambda m: audit_arg(m.group(1).split(":")), line)
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def needs_requote(text: str) -> bool:
    return any(line.startswith("Exec=") and 'LD_AUDIT="' in line for line in text.splitlines())


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
    audit = audit_arg(targets)
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
    entry = _sls_entry(audit)
    if entry is not None:
        (apps / SLS_ENTRY).write_text(entry)
        wrote = True
    if wrote:
        try:
            subprocess.run(["update-desktop-database", str(apps)], capture_output=True)
        except Exception:
            pass
    return targets


def _sls_entry(audit: str) -> str | None:
    """the SLSsteam app-menu entry, wired to the real steam binary. skipped when steam isn't a
    plain executable, because LD_AUDIT can't reach inside a flatpak or a snap."""
    from ..steam.find import find_steam

    try:
        found = find_steam()
    except (ImportError, OSError):
        found = None
    binary = (found.binary if found else None) or shutil.which("steam")
    if not binary or " " in binary:
        return None
    return (
        "[Desktop Entry]\n"
        "Name=SLSsteam\n"
        "Comment=Steam with SLSsteam injected (paws)\n"
        f"Exec=env {audit} {binary} %U\n"
        "Icon=steam\n"
        "Terminal=false\n"
        "Type=Application\n"
        "Categories=Game;\n"
        "StartupWMClass=Steam\n"
        "MimeType=x-scheme-handler/steam;\n"
    )


def strip_ld_audit(text: str) -> str:
    """remove the injection paws added, leaving the launcher otherwise as it was.

    uninstall used to delete ~/.local/share/applications/steam.desktop outright. when the system
    has its own copy that works out the same by accident, but a steam.desktop the user had edited
    was destroyed, and "uninstall slssteam" should not cost you your steam launcher.
    """
    out = []
    for line in text.splitlines():
        plain = _plain(line)
        found = _AUDIT_ARG.search(plain) if line.startswith("Exec=") else None
        if found:
            head, tail = plain[: found.start()], plain[found.end() :]
            tail = tail.lstrip().lstrip(":").lstrip()
            cleaned = f"{head}{tail}".strip() if tail else head.rstrip()
            if cleaned.startswith("Exec=env") and cleaned.strip() == "Exec=env":
                cleaned = cleaned.replace("Exec=env", "Exec=steam %U")
            out.append(_escaped(cleaned))
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
        for value in audit_values(text):
            if value not in seen:
                seen.add(value)
                out.append((f, value.split(":")))
    return out
