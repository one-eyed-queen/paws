from __future__ import annotations

import shutil
from pathlib import Path

from ..paths import HOME
from ..util import pkgmgr
from .desktop import sls_launchers, strip_ld_audit
from .model import SlsInstall

APPS = HOME / ".local/share/applications"
SYSTEM_APPS = Path("/usr/share/applications")


def paws_owns(lib_dir):
    if (lib_dir / "paws.info.json").exists():
        return True
    return lib_dir in (
        HOME / ".local/share/SLSsteam",
        HOME / ".var/app/com.valvesoftware.Steam/.local/share/SLSsteam",
    )


def restore_launchers():
    """put steam's own launchers back the way they were, rather than deleting them.

    uninstall used to remove ~/.local/share/applications/steam.desktop. where the system has its
    own copy that ends up equivalent by accident, but an edited one was lost, and "remove
    slssteam" should never cost you your steam launcher.
    """
    restored = []
    for name in ("steam.desktop", "steam-native.desktop"):
        override = APPS / name
        if not override.exists():
            continue
        if (SYSTEM_APPS / name).exists():
            override.unlink(missing_ok=True)  # the untouched system copy takes over again
            restored.append(f"{name} back to the system one")
            continue
        try:
            text = override.read_text()
        except OSError:
            continue
        cleaned = strip_ld_audit(text)
        if "Exec=" in cleaned:
            override.write_text(cleaned)
            restored.append(f"{name} injection removed")
        else:
            override.unlink(missing_ok=True)
    return restored


def remove_sls_launchers() -> list[str]:
    """the SLSsteam-specific .desktop entries, which exist only to inject and so are SLSsteam's to
    remove. steam.desktop is not one of them and is restored, not deleted."""
    gone = []
    for f in sls_launchers():
        try:
            f.unlink()
        except OSError:
            continue
        gone.append(f.name)
    return gone


def purge_config() -> str | None:
    """set the config aside instead of deleting it. a full uninstall that silently threw away
    every setting and downloaded DLC is not something to do behind someone's back."""
    from ..paths import config_dirs

    for d in config_dirs():
        if not d.exists():
            continue
        backup = d.with_name(d.name + ".uninstalled")
        shutil.rmtree(backup, ignore_errors=True)
        try:
            d.rename(backup)
        except OSError:
            continue
        return str(backup)
    return None


def other_installs(keep: Path | None = None) -> list[str]:
    """SLSsteam installs that exist besides the one paws just wrote to."""
    from .find import find_all

    out: list[str] = []
    for one in find_all():
        if keep is not None and one.lib_dir == keep:
            continue
        who = one.managed_by or ("paws" if paws_owns(one.lib_dir) else "not installed by paws")
        out.append(f"{one.lib_dir} ({one.kind}, {who})")
    return out


def leftovers() -> list[str]:
    """what is still on the machine after paws' own copy is gone, in words fit to show a person."""
    from .desktop import launcher_targets
    from .find import find_all, lib_in

    out: list[str] = []
    for one in find_all():
        if one.managed_by:
            out.append(
                f"{one.managed_by} still has it at {one.lib_dir} - remove it with: "
                f"{pkgmgr.remove_hint('slssteam', one.managed_by)}"
            )
        else:
            owner = "paws" if paws_owns(one.lib_dir) else "not installed by paws"
            out.append(f"another copy is still at {one.lib_dir} ({owner})")
    for launcher, paths in launcher_targets():
        if any(lib_in(Path(p).parent) for p in paths):
            out.append(f"{launcher.name} still injects {':'.join(paths)}")
    return out


def uninstall(sls: SlsInstall | None, purge: bool = False) -> dict:
    """remove SLSsteam, and only SLSsteam.

    steam itself, its libraries and its settings are never touched. returns what happened so the
    caller can print it rather than a cheerful "done" that hides what is still on disk.
    """
    from .find import find_all

    report: dict = {"removed": [], "kept": [], "failed": [], "config_backup": None}
    if sls is not None and sls.kind == "windows":
        from ..windows import port

        report["removed"] = port.remove()
        return report

    found = find_all()
    if sls is not None and sls.lib_dir and all(one.lib_dir != sls.lib_dir for one in found):
        found.append(sls)  # the install the caller asked about, even where find_all doesn't look
    for one in found:
        if one.managed_by:
            if not purge:
                report["kept"].append(
                    f"{one.managed_by} owns {one.lib_dir} - {pkgmgr.remove_hint('slssteam', one.managed_by)}"
                )
                continue
            ok, why = pkgmgr.remove_package("slssteam", one.managed_by)
            # a removal that did not happen must never land in "removed" - that is how uninstall
            # ends up reporting success for work it never did
            (report["removed"] if ok else report["failed"]).append(why)
            continue
        if one.lib_dir and paws_owns(one.lib_dir):
            shutil.rmtree(one.lib_dir, ignore_errors=True)
            report["removed"].append(str(one.lib_dir))

    for name in remove_sls_launchers():
        report["removed"].append(f"{APPS}/{name}")
    for line in restore_launchers():
        report["removed"].append(line)

    if purge:
        report["config_backup"] = purge_config()
    return report


def uninstall_or_raise(sls: SlsInstall | None) -> bool:
    """kept for the windows path, which still reports a bare success/failure."""
    result = uninstall(sls)
    return bool(result["removed"])
