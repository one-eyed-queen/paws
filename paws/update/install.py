from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def reinstall(checkout: Path) -> tuple[bool, str]:
    base = [sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--disable-pip-version-check"]
    last = ""
    for extra in (["--no-build-isolation"], []):
        try:
            r = subprocess.run([*base, *extra, str(checkout)], capture_output=True, text=True, timeout=240)
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        if r.returncode == 0:
            _keep_minimal()
            return True, ""
        last = (r.stderr.strip().splitlines() or ["pip failed"])[-1]
    return False, last


def _keep_minimal():
    from .. import riced, settings

    if settings.get_setting("type") == "minimal":
        riced.prune()
