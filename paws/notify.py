from __future__ import annotations

import os
import shutil
import subprocess

from .paths import DATA_DIR

APP = "paws"
ICON = DATA_DIR / "img" / "paws-icon.png"
TIMEOUT_MS = 6000
URGENCY = ("low", "normal", "critical")


def graphical() -> bool:
    return os.name == "nt" or bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def disabled() -> bool:
    return bool(os.environ.get("PAWS_NO_NOTIFY"))


def backend() -> str | None:
    if os.name == "nt":
        from .windows import toast

        return "powershell" if toast.available() else None
    if shutil.which("notify-send"):
        return "notify-send"
    if shutil.which("gdbus"):
        return "gdbus"
    return None


def _gv_string(text):
    """a string as gdbus wants it single quotes and escaped backslashes"""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def command(title: str, body: str = "", urgency: str = "normal", which: str | None = None) -> list[str] | None:
    which = which or backend()
    urgency = urgency if urgency in URGENCY else "normal"
    if which == "powershell":
        from .windows import toast

        return toast.command(title, body, urgency, TIMEOUT_MS)
    icon = str(ICON) if ICON.exists() else "dialog-information"
    if which == "notify-send":
        from .settings import get_setting

        argv = ["notify-send", "-a", APP, "-i", icon, "-u", urgency, "-t", str(TIMEOUT_MS)]
        if not get_setting("notify_sound"):
            argv += ["-h", "boolean:suppress-sound:true"]
        argv += ["--", title]
        if body:
            argv.append(body)
        return argv
    if which == "gdbus":
        return [
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.Notifications",
            "--object-path", "/org/freedesktop/Notifications",
            "--method", "org.freedesktop.Notifications.Notify",
            _gv_string(APP), "0", _gv_string(icon), _gv_string(title), _gv_string(body), "[]", "{}", str(TIMEOUT_MS),
        ]  # fmt: skip
    return None


def send(title: str, body: str = "", urgency: str = "normal") -> bool:
    if disabled() or not graphical():
        return False
    argv = command(title, body, urgency)
    if argv is None:
        return False
    try:
        if os.name == "nt":  # the balloon has to stay up a moment, don't make the caller wait for it
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
            return True
        r = subprocess.run(
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, start_new_session=True
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0
