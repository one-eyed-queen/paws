from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from ... import games
from ..widgets.header import AppHeader
from ..widgets.modals import Confirm


class RemoveGameScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("Remove a game", id="hdr")
        yield Input(placeholder="AppId to remove", id="in-rid")
        with Horizontal(id="remove-actions"):
            yield Button("Preview + Remove", id="b-preview")
            yield Button("Bulk...", id="b-bulk")
        yield Static("", id="remove-out", classes="panel")

    def on_mount(self):
        self.query_one("#in-rid", Input).focus()

    @on(Button.Pressed, "#b-bulk")
    def _bulk(self):
        from .bulk import BulkScreen

        self.app.push_screen(BulkScreen())

    @on(Button.Pressed, "#b-preview")
    def _preview(self):
        appid = self.query_one("#in-rid", Input).value.strip()
        if not appid:
            return
        plan = games.plan_remove(appid)
        self.query_one("#remove-out", Static).update("will remove:\n" + "\n".join(plan.notes) + "\n\nproceed?")
        self.app.push_screen(Confirm(f"Remove all SLS entries for AppId {appid}?", dangerous=True), self._do_remove)

    def _do_remove(self, yes):
        if yes:
            appid = self.query_one("#in-rid", Input).value.strip()
            result = games.apply_remove(games.plan_remove(appid))
            self.query_one("#remove-out", Static).update(f"[green]done[/green]: {result}")
            self.app.tell(f"{appid} removed", f"{result.get('removed', 0)} entries taken out")

    def action_pop(self):
        self.app.pop_screen()
