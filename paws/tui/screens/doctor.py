from __future__ import annotations

import time

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from ... import repair
from ..widgets.modals import Confirm
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar


class DoctorScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Status / Doctor", id="hdr")
        with VerticalScroll(id="doctor-scroll"):
            yield Static("", id="doctor-body")
        yield JobBar(id="job")
        with Horizontal():
            yield Button("Re-run", id="btn-redoc")
            yield Button("Repair...", id="btn-repair")
            yield Button("Reset config", id="btn-reset", variant="error")
            yield Button("Clear tickets", id="btn-clear", variant="error")
            yield Button("Back", id="btn-back")

    def on_mount(self):
        self._draw()
        self.set_interval(0.25, self._draw)

    @on(Button.Pressed, "#btn-redoc")
    def _rerun(self):
        self.run_checks()

    @on(Button.Pressed, "#btn-repair")
    def _repair(self):
        from .repair import RepairScreen

        self.app.push_screen(RepairScreen())

    @on(Button.Pressed, "#btn-reset")
    def _reset(self):
        self.app.push_screen(
            Confirm(
                "Replace config.yaml with the latest one SLSsteam ships?\nyour games and settings in it go away, "
                "the old file is kept in the backups.",
                "Reset config",
                dangerous=True,
            ),
            lambda yes: self._do(repair.reset_config) if yes else None,
        )

    @on(Button.Pressed, "#btn-clear")
    def _clear(self):
        self.app.push_screen(
            Confirm("Delete every cached ticket?\ncopies are kept in the backups.", "Clear tickets", dangerous=True),
            lambda yes: self._do(repair.clear_tickets) if yes else None,
        )

    def _do(self, action):
        self.app.run_job("fixing", lambda progress: action(), self._did)

    def _did(self, message):
        self.app.tell(str(message), "", "error" if isinstance(message, Exception) else "information")
        if self.is_attached:
            self.run_checks()

    @on(Button.Pressed, "#btn-back")
    def _back(self):
        self.action_pop()

    def run_checks(self):
        self.app.run_doctor()
        self._drawn = -1

    _drawn = -1

    def _draw(self):
        """shows whatever the app already knows, so opening this page does no checking of its own"""
        report = self.app.doctor_report
        busy = self.app.doctor_busy
        count = len(report.checks) if report else 0
        if (count, busy) == self._drawn:
            return
        self._drawn = (count, busy)
        lines = [self._row(check) for check in report.checks] if report else []
        if busy:
            lines.append("[#d5deff]checking...[/]")
        elif self.app.doctor_at:
            lines.append(f"[#9aa5c4]checked {time.strftime('%H:%M:%S', time.localtime(self.app.doctor_at))}, Re-run checks again[/]")
        self.query_one("#doctor-body", Static).update("\n".join(lines))

    @staticmethod
    def _row(check):
        sym = {"ok": "[b #5ff0a0]OK[/]", "warn": "[b #ffd75f]WARN[/]", "error": "[b #ff7a8a]FAIL[/]"}.get(check.severity, " ")
        return f"{sym} [b]{escape(check.label)}[/b]: [#d5deff]{escape(check.detail)}[/]"

    def action_pop(self):
        self.app.pop_screen()
