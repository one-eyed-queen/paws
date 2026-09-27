from __future__ import annotations

from contextlib import contextmanager

from rich.console import Console
from rich.text import Text

from .. import __version__
from .repo import short_name

WIDTH_MIN, WIDTH_MAX = 44, 78


class Colors:
    primary = "bold"
    secondary = "cyan"
    fg = "default"
    muted = "dim"
    success = "green"
    warning = "yellow"
    error = "red"


class Splash:
    def __init__(self, console: Console | None = None):
        self.s = Colors()
        self.console = console or Console()
        self.width = max(WIDTH_MIN, min(WIDTH_MAX, self.console.width - 2))

    def _rule(self):
        return Text(" " + "─" * self.width, self.s.muted)

    def header(self):
        left = Text(" ")
        left.append("▌", self.s.primary)
        left.append("PAWS", f"bold {self.s.primary}")
        left.append("▐", self.s.primary)
        left.append("  SLSsteam manager", self.s.muted)
        right = f"v{__version__}"
        pad = max(1, self.width + 1 - len(left.plain) - len(right))
        left.append(" " * pad)
        left.append(right, self.s.secondary)
        self.console.print()
        self.console.print(left)
        self.console.print(self._rule())

    def row(self, label: str, detail: str, value: str, color: str):
        t = Text("  ")
        t.append(f"{label:<7}", f"bold {self.s.secondary}")
        t.append(" " + detail + " ", self.s.fg)
        gap = max(2, self.width + 1 - len(t.plain) - len(value) - 1)
        t.append("·" * gap, self.s.muted)
        t.append(" " + value, f"bold {color}")
        self.console.print(t)

    def note(self, text: str, color: str | None = None):
        self.console.print(Text("          " + text, color or self.s.muted))

    @contextmanager
    def working(self, label: str, detail: str):
        with self.console.status(
            Text.assemble(("  ", ""), (f"{label:<7}", f"bold {self.s.secondary}"), (" " + detail, self.s.muted)),
            spinner="dots",
            spinner_style=self.s.primary,
        ):
            yield

    def show(self, status):
        from . import git

        s = self.s
        repo = short_name()
        build = git.short(status.local)
        kind = status.state
        if kind == "current":
            self.row("UPLINK", repo, "ONLINE", s.success)
            self.row("BUILD", build, "CURRENT", s.success)
        elif kind == "updated":
            self.row("UPLINK", repo, "ONLINE", s.success)
            self.row("BUILD", f"{build} → {git.short(status.remote)}", "UPDATED", s.primary)
            for line in status.subjects[:3]:
                self.note("+ " + line[: self.width - 14])
        elif kind == "behind":
            self.row("UPLINK", repo, "ONLINE", s.success)
            self.row("BUILD", f"{build} → {git.short(status.remote)}", "BEHIND", s.warning)
        elif kind == "blocked":
            self.row("UPLINK", repo, "ONLINE", s.success)
            self.row("BUILD", build, "HELD", s.warning)
            self.note(status.message, s.warning)
        elif kind == "offline":
            self.row("UPLINK", repo, "OFFLINE", s.muted)
            self.note("skipping the update check", s.muted)
        elif kind == "error":
            self.row("BUILD", build, "ERROR", s.error)
            self.note(status.message, s.error)
