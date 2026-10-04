"""opening paws in its own window on windows: windows terminal when it's there, else a plain console window.
no shell strings in between (cmd's quoting rules would eat paths with spaces), paws keeps the window open
itself on an error via PAWS_HOLD"""

from __future__ import annotations

import shutil
from collections.abc import Mapping

from ..launch.argv import TITLE

NEW_CONSOLE = 0x00000010  # CREATE_NEW_CONSOLE
HOLD = "PAWS_HOLD"

ORDER = ("wt", "console")


def current_terminal(env: Mapping[str, str]) -> str | None:
    if env.get("WT_SESSION"):
        return "wt"
    if (env.get("TERM_PROGRAM") or "").lower() == "vscode":
        return "vscode"
    return "console" if env.get("PROMPT") or env.get("PSModulePath") else None


def installed(name: str, env: Mapping[str, str] | None = None) -> bool:
    if name == "console":
        return True
    return bool(shutil.which(name, path=(env or {}).get("PATH")))


def candidates(env: Mapping[str, str], wanted: list[str | None]) -> list[str]:
    out = []
    for name in [*wanted, *ORDER]:
        if name and name not in out and installed(name, env):
            out.append(name)
    return out


def build_argv(terminal: str, argv: list[str]) -> list[str]:
    if terminal == "wt":
        return ["wt", "--title", TITLE, *argv]
    return list(argv)


def creation_flags(terminal: str) -> int:
    return NEW_CONSOLE if terminal == "console" else 0
