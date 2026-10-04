from __future__ import annotations

import os

from ..util import distro
from ..util import pkgmgr
from .result import CheckResult


def os_checks(d=None) -> list:
    if d is None and os.name == "nt":
        import platform

        found = pkgmgr.available()
        return [
            CheckResult(
                True, "OS", f"Windows {platform.release()} {platform.machine()} ({platform.version()})", "info"
            ),
            CheckResult(True, "Package managers", ", ".join(found) if found else "none found", "info"),
        ]
    d = d or distro.detect()
    out = [CheckResult(True, "OS", f"{d.name} ({d.id}, {d.family} family)", "info")]
    found = pkgmgr.available()
    out.append(CheckResult(True, "Package managers", ", ".join(found) if found else "none found", "info"))
    if d.immutable:
        out.append(CheckResult(True, "Read-only system", d.immutable_note, "info"))
    return out


def steam_checks(steam) -> list:
    out = os_checks()
    if not steam:
        hints = pkgmgr.install_hints("steam")
        how = "  |  ".join(hints) if hints else "install steam with your package manager"
        out.append(CheckResult(False, "Steam NOT detected", f"run steam once, or install it: {how}", "error"))
        return out
    out.append(
        CheckResult(
            True,
            "Steam detected",
            f"{steam.kind} root={steam.root} ver={steam.client_version} chan={steam.channel}"
            + (f" pkg={steam.package}" if steam.package else ""),
            "ok",
        )
    )
    if steam.kind in ("flatpak", "snap"):
        out.append(
            CheckResult(
                True,
                f"{steam.kind} Steam",
                "paws can read and edit its files, but can't wire SLSsteam into the sandbox for you",
                "info",
            )
        )
    if steam.is_running:
        out.append(CheckResult(True, "Steam running", "steam process is active", "info"))
    return out
