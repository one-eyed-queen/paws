from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, RadioButton, RadioSet, Static

from ... import settings as settingsmod
from ... import shellalias as sa
from ...util import clipboard
from ..widgets.footer import FooterHelp
from ..widgets.header import AppHeader


class AliasScreen(Screen):
    DEFAULT_CLASSES = "page"

    BINDINGS = [Binding("escape", "pop", "back"), Binding("backspace", "pop", "back", show=False)]

    def compose(self) -> ComposeResult:
        yield AppHeader("Shell alias", id="hdr")
        with Vertical(id="alias-box", classes="panel"):
            yield Static("[#9db0e0]the command you type to start paws[/]", id="alias-help")
            yield Input(value=str(settingsmod.get_setting("launch_cmd") or "paws"), placeholder="paws", id="alias-name")
            with RadioSet(id="alias-shell"):
                mine = str(settingsmod.get_setting("alias_shell") or "") or sa.my_shell()
                for shell in sa.SHELLS:
                    yield RadioButton(shell, value=shell == mine, name=shell)
            yield Static("", id="alias-snippet", markup=False)
            with Horizontal(id="alias-buttons"):
                yield Button("Put it in my shell config", id="alias-install", variant="primary")
                yield Button("Copy the snippet", id="alias-copy")
                yield Button("Fix PATH (~/.local/bin)", id="alias-path")
        yield Static("", id="alias-out", classes="panel")
        yield FooterHelp("type the name · pick your shell · enter or tab to the buttons · esc back")

    def on_mount(self):
        self.query_one("#alias-name", Input).focus()
        self._show()
        self.say("")

    def cmd(self) -> str:
        return self.query_one("#alias-name", Input).value.strip()

    def shell(self) -> str:
        pressed = self.query_one("#alias-shell", RadioSet).pressed_button
        return (pressed.name if pressed is not None else None) or sa.my_shell()

    def _show(self):
        name = self.cmd()
        box = self.query_one("#alias-snippet", Static)
        if not sa.valid_name(name):
            box.update("letters, digits, - and _ only (not starting with a digit)")
            return
        box.update(sa.snippet(self.shell(), name))

    def say(self, text: str):
        self.query_one("#alias-out", Static).update(text or "[#9db0e0]nothing is written until you press a button[/]")

    @on(Input.Changed, "#alias-name")
    def _changed(self):
        self._show()

    @on(RadioSet.Changed, "#alias-shell")
    def _shell_changed(self):
        settingsmod.set_setting("alias_shell", self.shell())
        self._show()

    @on(Input.Submitted, "#alias-name")
    def _submitted(self):
        self.query_one("#alias-install", Button).focus()

    @on(Button.Pressed, "#alias-install")
    def _install(self):
        try:
            r = sa.install_function(self.shell(), self.cmd())
        except ValueError as e:
            self.say(f"[red]{e}[/red]")
            return
        self.say(f"{r.note} in {r.file}" + ("   [#9db0e0]open a new terminal for it to work[/]" if r.changed else ""))

    @on(Button.Pressed, "#alias-copy")
    def _copy(self):
        if not sa.valid_name(self.cmd()):
            self.say("[red]fix the command name first[/red]")
            return
        ok = clipboard.copy(sa.snippet(self.shell(), self.cmd()))
        self.say("copied the snippet" if ok else "couldn't reach the clipboard: select it above and copy it")

    @on(Button.Pressed, "#alias-path")
    def _path(self):
        r = sa.install_path(self.shell())
        self.say(f"{r.note} in {r.file}" + ("   [#9db0e0]open a new terminal for it to work[/]" if r.changed else ""))

    def action_pop(self):
        self.app.pop_screen()
