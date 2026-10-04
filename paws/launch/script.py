from __future__ import annotations

import os
import shlex
import shutil
import sys

from .argv import TITLE


def paws_argv() -> list[str]:
    exe = shutil.which("paws")
    if exe:
        return [os.path.realpath(exe), "menu"]
    if sys.executable:
        sibling = os.path.join(os.path.dirname(sys.executable), "paws.exe" if os.name == "nt" else "paws")
        if os.path.exists(sibling):
            return [sibling, "menu"]
        scripts = os.path.join(os.path.dirname(sys.executable), "Scripts", "paws.exe")  # windows venv/python layout
        if os.name == "nt" and os.path.exists(scripts):
            return [scripts, "menu"]
        return [sys.executable, "-m", "paws", "menu"]
    return ["python3", "-m", "paws", "menu"]


def shell_command(argv: list[str] | None = None) -> str:
    run = " ".join(shlex.quote(a) for a in (argv or paws_argv()))
    return (
        f"printf '\\033]0;{TITLE}\\007'; {run}; rc=$?; "
        'if [ "$rc" -ne 0 ]; then '
        'printf "\\npaws exited with code %s\\npress Enter to close " "$rc"; read _; '
        'fi; exit "$rc"'
    )
