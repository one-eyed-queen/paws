from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import threading
from typing import Callable

Approver = Callable[[list[str], str], bool]

_KEY = ["service", "paws", "account", "sudo"]
_cached: str | None = None


def _keyring(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess | None:
    if not shutil.which("secret-tool"):
        return None
    try:
        # a locked keyring can sit on an unlock dialog forever
        return subprocess.run(["secret-tool", *args], input=stdin, text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


def _keyring_get() -> str | None:
    r = _keyring(["lookup", *_KEY])
    return r.stdout.rstrip("\n") or None if r and r.returncode == 0 else None


def _keyring_set(password: str) -> bool:
    r = _keyring(["store", "--label=paws sudo password", *_KEY], password)
    return bool(r and r.returncode == 0)


def forget() -> bool:
    """drop the saved password from the keyring and from this process"""
    global _cached
    _cached = None
    r = _keyring(["clear", *_KEY])
    return bool(r and r.returncode == 0)


def _sudo_ok() -> bool:
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _valid(password: str) -> bool:
    try:
        r = subprocess.run(
            ["sudo", "-k", "-S", "-p", "", "true"], input=password + "\n", text=True, capture_output=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _can_prompt() -> bool:
    # a worker thread under the TUI shares the terminal with it, and getpass would hang unseen
    return threading.current_thread() is threading.main_thread() and sys.stdin.isatty()


def ensure_root(detail: str = "paws needs root for this") -> str | None:
    """the password sudo needs, "" if it needs none, None if root isn't available.

    asks once, then keeps it in the desktop keyring so later runs don't ask again. with no keyring
    it lasts for this process only.
    """
    global _cached
    if os.geteuid() == 0 or _sudo_ok():
        return ""
    if _cached is not None and _valid(_cached):
        return _cached
    saved = _keyring_get()
    if saved is not None:
        if _valid(saved):
            _cached = saved
            return saved
        forget()  # the account password changed
    if not _can_prompt():
        return None
    print(f"\n[paws] {detail}\nyour sudo password is saved in the desktop keyring, so this is only asked once.\n"
          "`paws sls forget-root` removes it.\n", file=sys.stderr)
    for _ in range(3):
        try:
            password = getpass.getpass("sudo password: ")
        except (EOFError, KeyboardInterrupt):
            return None
        if not password:
            return None
        if _valid(password):
            _cached = password
            if not _keyring_set(password):
                print("[paws] no usable keyring, so this password lasts until paws closes", file=sys.stderr)
            return password
        print("that didn't work", file=sys.stderr)
    return None


def run_privileged_quiet(
    command: list[str], detail: str = "", timeout: float = 600, password: str | None = None
) -> tuple[int, str, str]:
    """-> (returncode, stdout, stderr). 130 means root wasn't available"""
    if not hasattr(os, "geteuid"):
        return 126, "", "windows: run this from an administrator terminal"
    if os.geteuid() == 0:
        full, stdin = command, None
    else:
        password = password if password is not None else ensure_root(detail)
        if password is None:
            return 130, "", "root wasn't available"
        full = ["sudo", "-n", *command] if password == "" else ["sudo", "-S", "-p", "", *command]
        stdin = password + "\n" if password else None
    try:
        r = subprocess.run(full, input=stdin, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", f"{full[0]} not found"
    except (OSError, subprocess.SubprocessError) as error:
        return 1, "", str(error)
    return r.returncode, r.stdout, r.stderr


def run_privileged(
    command: list[str], detail: str = "", approver: Approver | None = None, password: str | None = None
) -> int:
    if approver is not None and not approver(command, detail):
        return 130
    code, out, err = run_privileged_quiet(command, detail, password=password)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code
