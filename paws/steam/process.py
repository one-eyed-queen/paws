from __future__ import annotations

import os
import signal
import subprocess
import time


def _pgrep(*args):
    try:
        return subprocess.run(["pgrep", *args], capture_output=True, text=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []


def steam_pids():
    return _pgrep("-x", "steam")


def helper_pids():
    return _pgrep("-x", "steamwebhelper")


def _signal_all(pids, signal_number):
    for pid in pids:
        try:
            os.kill(int(pid), signal_number)
        except (ProcessLookupError, PermissionError, ValueError):
            continue


def kill_steam(timeout: float = 10.0) -> bool:
    pids = steam_pids() + helper_pids()
    if not pids:
        return False
    _signal_all(pids, signal.SIGTERM)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not (steam_pids() or helper_pids()):
            return True
        time.sleep(0.3)
    _signal_all(steam_pids() + helper_pids(), signal.SIGKILL)
    time.sleep(0.5)
    return not (steam_pids() or helper_pids())


def is_running() -> bool:
    return bool(steam_pids())
