from __future__ import annotations

import getpass
import os
import subprocess
import sys
from typing import Callable

Approver = Callable[[list[str], str], bool]


def _default_approver(command, detail):
    print(f"\n[privilege] {detail}\n$ {' '.join(command)}", file=sys.stderr)
    try:
        ans = input("Allow this with sudo? [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def run_privileged(
    command: list[str],
    detail: str = "",
    approver: Approver | None = None,
    password: str | None = None,
) -> int:
    if os.geteuid() == 0:
        return subprocess.run(command, text=True).returncode
    approver = approver or _default_approver
    if not approver(command, detail):
        print("[privilege] denied", file=sys.stderr)
        return 130
    passwd = password if password is not None else _prompt_password()
    try:
        r = subprocess.run(
            ["sudo", "-S", "-p", "", *command],
            input=passwd + "\n",
            text=True,
            capture_output=True,
        )
        sys.stderr.write(r.stderr)
        sys.stdout.write(r.stdout)
        return r.returncode
    except FileNotFoundError:
        return 127


def _prompt_password():
    if not sys.stdin.isatty():
        return ""
    return getpass.getpass("sudo password: ")
