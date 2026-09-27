from __future__ import annotations

import os
import shlex
from typing import Callable

TITLE = "paws"
CLASS = "paws"


def _line(command):
    return shlex.join(["sh", "-c", command])


_SPECS: dict[str, Callable[[str], list[str]]] = {
    "kitty": lambda c: ["kitty", "--class", CLASS, "--title", TITLE, "sh", "-c", c],
    "konsole": lambda c: ["konsole", "-e", "sh", "-c", c],
    "alacritty": lambda c: ["alacritty", "--class", CLASS, "--title", TITLE, "-e", "sh", "-c", c],
    "foot": lambda c: ["foot", "--app-id", CLASS, "--title", TITLE, "sh", "-c", c],
    "wezterm": lambda c: ["wezterm", "start", "--class", CLASS, "--", "sh", "-c", c],
    "ghostty": lambda c: ["ghostty", f"--class={CLASS}", f"--title={TITLE}", "-e", "sh", "-c", c],
    "gnome-terminal": lambda c: ["gnome-terminal", f"--title={TITLE}", "--", "sh", "-c", c],
    "xfce4-terminal": lambda c: ["xfce4-terminal", f"--title={TITLE}", "-x", "sh", "-c", c],
    "rio": lambda c: ["rio", "-e", "sh", "-c", c],
    "xterm": lambda c: ["xterm", "-class", CLASS, "-T", TITLE, "-e", "sh", "-c", c],
    "urxvt": lambda c: ["urxvt", "-title", TITLE, "-e", "sh", "-c", c],
    "xdg-terminal-exec": lambda c: ["xdg-terminal-exec", "sh", "-c", c],
    "ptyxis": lambda c: ["ptyxis", "--new-window", "--title", TITLE, "-x", _line(c)],
    "kgx": lambda c: ["kgx", "-e", _line(c)],
    "mate-terminal": lambda c: ["mate-terminal", "--title", TITLE, "-x", "sh", "-c", c],
    "tilix": lambda c: ["tilix", "-t", TITLE, "-e", _line(c)],
    "terminator": lambda c: ["terminator", "-T", TITLE, "-x", "sh", "-c", c],
    "lxterminal": lambda c: ["lxterminal", "-t", TITLE, "-e", "sh", "-c", c],
    "qterminal": lambda c: ["qterminal", "-e", _line(c)],
    "deepin-terminal": lambda c: ["deepin-terminal", "-e", _line(c)],
    "cosmic-term": lambda c: ["cosmic-term", "-e", "sh", "-c", c],
    "x-terminal-emulator": lambda c: ["x-terminal-emulator", "-e", "sh", "-c", c],
}


FALLBACK_ORDER = (
    "kitty",
    "konsole",
    "alacritty",
    "foot",
    "wezterm",
    "ghostty",
    "gnome-terminal",
    "ptyxis",
    "kgx",
    "xfce4-terminal",
    "mate-terminal",
    "tilix",
    "terminator",
    "lxterminal",
    "qterminal",
    "cosmic-term",
    "deepin-terminal",
    "rio",
    "xterm",
    "urxvt",
    "x-terminal-emulator",
)


def build_argv(terminal: str, command: str) -> list[str]:
    builder = _SPECS.get(os.path.basename(terminal))
    if builder is not None:
        argv = builder(command)
        argv[0] = terminal
        return argv
    return [
        terminal,
        "-e",
        "sh",
        "-c",
        command,
    ]
