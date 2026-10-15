from __future__ import annotations

from ..util import pkgmgr
from .result import CheckResult


def os_checks(d=None) -> list:
    # one os detector, shared with `paws info` and the home screen - this used to build the same
    # answer a second time here, which is how the two drifted apart
    from .. import detect

    seen = detect.detect_os()
    out = [CheckResult(True, "OS", seen.line(), "info")]
    found = seen.package_managers
    out.append(CheckResult(True, "Package managers", ", ".join(found) if found else "none found", "info"))
    if seen.immutable:
        out.append(CheckResult(True, "Read-only system", seen.immutable_note, "info"))
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
