"""python on windows reads and writes files as cp1252 unless it runs in utf-8 mode. config.yaml, config.vdf, game
names and the art are all utf-8, so paws restarts itself once in utf-8 mode instead of trusting every open() call"""

from __future__ import annotations

import os
import subprocess
import sys


def needed() -> bool:
    return sys.platform == "win32" and not sys.flags.utf8_mode and not os.environ.get("PAWS_NO_UTF8_RESTART")


def rerun(argv: list[str]) -> int:
    """same python, same args, utf-8 mode on. the child shares this console so the TUI just works"""
    env = {**os.environ, "PYTHONUTF8": "1", "PAWS_NO_UTF8_RESTART": "1"}
    # -P keeps the current folder off sys.path, so a paws/ folder in it can't stand in for the installed one
    safe = ["-P"] if sys.version_info >= (3, 11) else []
    try:
        return subprocess.call([sys.executable, "-X", "utf8", *safe, "-m", "paws", *argv], env=env)
    except KeyboardInterrupt:
        return 130
