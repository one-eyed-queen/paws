from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys


def _tools():
    wayland = ("wl-copy", [])
    x11 = [("xclip", ["-selection", "clipboard"]), ("xsel", ["--clipboard", "--input"])]
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return [wayland, *x11]
    return [*x11, wayland]


def _run(tool, flags, text):
    try:
        r = subprocess.run(
            [tool, *flags],
            input=text.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return True
    except Exception:
        return False
    return r.returncode == 0


def _windows_copy(text):
    """clip.exe takes utf-16 with a BOM as unicode, anything else it reads in the console codepage"""
    try:
        r = subprocess.run(
            ["clip"],
            input=("\ufeff" + text).encode("utf-16-le"),
            capture_output=True,
            timeout=5,
            creationflags=0x08000000,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def copy(text: str) -> bool:
    if os.name == "nt" and _windows_copy(text):
        return True
    for tool, flags in _tools():
        if shutil.which(tool) and _run(tool, flags, text):
            return True
    if sys.stdout.isatty():
        b64 = base64.b64encode(text.encode()).decode()
        try:
            sys.stdout.write(f"\x1b]52;c;{b64}\x07")
            sys.stdout.flush()
            return True
        except Exception:
            pass
    return False
