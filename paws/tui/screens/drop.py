from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from ... import drop
from ..widgets import dropzone
from ..widgets.backdrop import SCREEN_BLUR, Backdrop

SHOW_RESULT_FOR = 2.6


class DropScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "close", "back"),
        ("q", "close", "back"),
        ("ctrl+d", "close", "back"),
    ]

    def __init__(self, result: drop.DropResult | None = None, **kwargs):
        super().__init__(**kwargs)
        self._result = result
        self._timer = None

    def _texts(self):
        r = self._result
        if r is None:
            return dropzone.CAPTION, dropzone.HINT, "wait"
        hint = " · ".join(line for line in r.lines if line)[:160] or ""
        return r.title, hint, "ok" if r.ok else "bad"

    def compose(self) -> ComposeResult:
        with Container(id="drop-card"):
            yield Static(self._card_text(), id="drop-text", markup=True)

    def _card_text(self):
        caption, hint, state = self._texts()
        colour = {"wait": "#00d0ff", "ok": "#3ddc97", "bad": "#ff5c7a"}[state]
        glyph = {"wait": "+", "ok": "✓", "bad": "✕"}[state]
        sp = " "
        box = f"╭─────╮\n│{sp * 2}{glyph}{sp * 2}│\n╰─────╯"
        return f"[{colour}]{box}[/]\n\n[b]{caption}[/b]\n[#9db0e0]{hint}[/]"

    def on_mount(self):
        bd = Backdrop(dropzone.BG, base=(10, 16, 32), strength=0.5, blur=SCREEN_BLUR / 2)
        self.backdrop = bd if bd.load() else None
        if self._result is not None:
            self._timer = self.set_timer(SHOW_RESULT_FOR, self.action_close)

    def show_result(self, result: drop.DropResult):
        self._result = result
        self.query_one("#drop-text", Static).update(self._card_text())
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(SHOW_RESULT_FOR, self.action_close)

    def action_close(self):
        if self.is_current:
            self.dismiss(None)

    def on_click(self):
        self.action_close()
