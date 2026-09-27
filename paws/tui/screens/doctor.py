from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from ... import doctor, repair
from ..widgets.modals import Confirm
from ..widgets.header import AppHeader
from ..widgets.jobbar import JobBar


class DoctorScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Status / Doctor", id="hdr")
        yield VerticalScroll(id="doctor-scroll")
        yield JobBar(id="job")
        with Horizontal():
            yield Button("Re-run", id="btn-redoc")
            yield Button("Repair...", id="btn-repair")
            yield Button("Reset config", id="btn-reset", variant="error")
            yield Button("Clear tickets", id="btn-clear", variant="error")
            yield Button("Back", id="btn-back")

    def on_mount(self):
        self.run_checks()

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
        body = self.query_one("#doctor-scroll", VerticalScroll)
        body.remove_children()
        body.mount(Static("[#9db0e0]checking...[/]"))
        self._run_checks()

    @work(thread=True, exclusive=True, group="doctor")
    def _run_checks(self):
        report = doctor.run()
        self.app.call_from_thread(self._show, report)

    def _show(self, report):
        body = self.query_one("#doctor-scroll", VerticalScroll)
        body.remove_children()
        for check in report.checks:
            sym = {"ok": "[green]OK[/green]", "warn": "[yellow]WARN[/yellow]", "error": "[red]FAIL[/red]"}.get(
                check.severity, " "
            )
            body.mount(Static(f"{sym} [b]{check.label}[/b]: [#9db0e0]{check.detail}[/]"))

    def action_pop(self):
        self.app.pop_screen()
