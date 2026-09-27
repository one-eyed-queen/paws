from __future__ import annotations

from textual import on
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea


class ModalInput(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "cancel")]

    def __init__(self, prompt: str, title: str = "Input", default: str = "", password: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.prompt = prompt
        self.title = title
        self.default = default
        self.password = password

    def compose(self):
        with Container(id="modal-input"):
            yield Label(f"[b]{self.title}[/b]\n[#9db0e0]{self.prompt}[/]", id="mi-prompt")
            yield Input(value=self.default, placeholder="type here...", id="mi-value", password=self.password)
            with Horizontal(id="mi-buttons"):
                yield Button("OK", variant="primary", id="mi-ok")
                yield Button("Cancel", variant="error", id="mi-cancel")

    def on_mount(self):
        self.query_one("#mi-value", Input).focus()

    @on(Button.Pressed, "#mi-ok")
    def _ok(self):
        self.dismiss(self.query_one("#mi-value", Input).value)

    @on(Button.Pressed, "#mi-cancel")
    def _cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#mi-value")
    def _enter(self):
        self.dismiss(self.query_one("#mi-value", Input).value)

    def action_cancel(self):
        self.dismiss(None)


class Confirm(ModalScreen[bool]):
    BINDINGS = [
        Binding("escape", "no", "no"),
        Binding("n", "no", "no", show=False),
        Binding("y", "yes", "yes", show=False),
    ]

    def __init__(self, message: str, title: str = "Confirm", dangerous: bool = False):
        super().__init__()
        self.message = message
        self.title = title
        self.dangerous = dangerous

    def compose(self):
        with Container(id="modal-confirm"):
            yield Label(f"[{'bold red' if self.dangerous else 'b'}]{self.title}[/]\n\n{self.message}", id="c-msg")
            with Horizontal(id="c-buttons"):
                yield Button("Yes", variant="error" if self.dangerous else "primary", id="c-yes")
                yield Button("No", variant="error", id="c-no")

    @on(Button.Pressed, "#c-yes")
    def _yes(self):
        self.dismiss(True)

    @on(Button.Pressed, "#c-no")
    def _no(self):
        self.dismiss(False)

    def action_no(self):
        self.dismiss(False)

    def action_yes(self):
        self.dismiss(True)


class ModalInfo(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("enter", "close", "close", show=False),
        Binding("q", "close", "close", show=False),
    ]

    def __init__(self, text: str, title: str = "Info", copy: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.title = title
        self.copy_text = copy

    def compose(self):
        with Container(id="modal-info"):
            yield Label(f"[b]{self.title}[/b]", id="mn-title")
            yield Label(self.text, id="mn-text", markup=False)
            with Horizontal(id="mn-buttons"):
                if self.copy_text is not None:
                    yield Button("Copy", id="mn-copy")
                yield Button("Close", variant="primary", id="mn-close")

    def on_mount(self):
        self.query_one("#mn-close", Button).focus()

    @on(Button.Pressed, "#mn-copy")
    def _copy(self):
        from ...util import clipboard

        ok = clipboard.copy(self.copy_text or "")
        self.app.tell("copied" if ok else "couldn't copy", "", "information" if ok else "error")

    @on(Button.Pressed, "#mn-close")
    def _close(self):
        self.dismiss(None)

    def action_close(self):
        self.dismiss(None)


class ModalPaste(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "cancel"), Binding("ctrl+s", "ok", "ok", show=False)]

    def __init__(self, prompt: str, title: str = "Paste", **kwargs):
        super().__init__(**kwargs)
        self.prompt = prompt
        self.title = title

    def compose(self):
        with Container(id="modal-paste"):
            yield Label(f"[b]{self.title}[/b]\n[#9db0e0]{self.prompt}[/]", id="mp-prompt")
            yield TextArea("", id="mp-text")
            with Horizontal(id="mp-buttons"):
                yield Button("Import", variant="primary", id="mp-ok")
                yield Button("Cancel", variant="error", id="mp-cancel")

    def on_mount(self):
        self.query_one("#mp-text", TextArea).focus()

    @on(Button.Pressed, "#mp-ok")
    def action_ok(self):
        self.dismiss(self.query_one("#mp-text", TextArea).text)

    @on(Button.Pressed, "#mp-cancel")
    def action_cancel(self):
        self.dismiss(None)
