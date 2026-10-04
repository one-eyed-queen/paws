from __future__ import annotations

import os
import sys
from typing import Callable

from .. import settings
from . import state
from .splash import Splash
from .status import Status, apply, check, record

JUST_UPDATED = "PAWS_JUST_UPDATED"


def enabled() -> bool:
    if os.environ.get("PAWS_NO_UPDATE") or os.environ.get(JUST_UPDATED):
        return False
    if not settings.get_setting("auto_update"):
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def restart(argv: list[str]):  # pragma: no cover - replaces the process
    env = {**os.environ, JUST_UPDATED: "1"}
    if os.name == "nt":
        # windows has no real exec: os.execve starts a second process and this one exits under it, which hands the
        # console back to the shell mid-TUI. run the new build as a child and leave with its exit code instead
        import subprocess

        safe = ["-P"] if sys.version_info >= (3, 11) else []
        sys.exit(subprocess.call([sys.executable, "-X", "utf8", *safe, "-m", "paws", *argv], env=env))
    script = os.path.join(os.path.dirname(sys.executable), "paws")
    if os.path.exists(script):
        os.execve(script, [script, *argv], env)
    os.execve(sys.executable, [sys.executable, "-m", "paws", *argv], env)


def run(
    argv: list[str], splash: Splash | None = None, restarter: Callable[[list[str]], None] = restart
) -> Status | None:
    if not enabled():
        return None
    interval = float(settings.get_setting("update_interval_min") or 5)
    if state.fresh(interval):
        return None
    splash = splash or Splash()
    splash.header()
    with splash.working("UPLINK", "checking for a newer build"):
        status = check()
    if status.can_apply:
        splash.show(status)
        with splash.working("BUILD", "installing"):
            status = apply(status)
    record(status)
    splash.show(status)
    splash.console.print()
    if status.state == "updated":
        splash.note("restarting into the new build", splash.s.primary)
        restarter(argv)
    return status
