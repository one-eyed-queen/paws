from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from ... import art
from ..widgets.art_panel import AsciiPanel
from ..widgets.footer import FooterHelp
from ..widgets.header import AppHeader
from ..widgets.menu import Menu, MenuItem


class ArtScreen(Screen):
    DEFAULT_CLASSES = "page"
    BINDINGS = [("escape", "pop", "back"), ("backspace", "pop", "back")]

    def compose(self) -> ComposeResult:
        yield AppHeader("ASCII art / home banner", id="hdr")
        with Horizontal(id="art-row"):
            yield Menu(id="art-menu", classes="panel")
            with Vertical(id="art-right"):
                yield AsciiPanel(id="art-preview")
                with Horizontal(id="art-bar", classes="glass"):
                    yield Static("", id="art-info")
                    yield Button("Use as banner", variant="primary", id="b-set")
                    yield Button("Back", id="b-back")
        yield FooterHelp("↑↓ look through them · enter uses one as the home banner · esc back")

    def on_mount(self):
        self.arts = art.library()
        self._current = None
        m = self.query_one("#art-menu", Menu)
        now = art.banner_name()
        for key in sorted(self.arts):
            a = self.arts[key]
            m.append(MenuItem(key, self._label(key, now), a.title or f"{len(a.lines)} lines", "art"))
        if m.children:
            m.focus()
            names = sorted(self.arts)
            start = names.index(now) if now in names else 0
            m.index = start
            self._show(names[start])

    @on(Menu.Highlighted)
    def _hi(self, ev):
        if ev.item:
            self._show(ev.item.data)

    @on(Menu.Selected)
    def _sel(self, ev):
        if ev.item:
            self._use(ev.item.data)

    @on(Button.Pressed, "#b-set")
    def _btn_set(self):
        if self._current:
            self._use(self._current)

    @on(Button.Pressed, "#b-back")
    def _back(self):
        self.action_pop()

    def _show(self, key):
        self._current = key
        piece = self.arts.get(key)
        rows = len(piece.lines) if piece else 0
        cols = max((len(line) for line in piece.lines), default=0) if piece else 0
        now = art.banner_name()
        tag = "  [#ffd75f]★ home banner[/]" if key == now else ""
        self.query_one("#art-info", Static).update(f"[b]{key}[/b]  [#9db0e0]{cols}x{rows}[/]{tag}")
        self.query_one("#art-preview", AsciiPanel).pending(key, piece)
        self._draw_preview(key, piece)

    @work(thread=True, exclusive=True, group="art-preview")
    def _draw_preview(self, key, piece):
        panel = self.query_one("#art-preview", AsciiPanel)
        size = panel.content_size
        if not size.width or not size.height:
            return
        chosen = piece if (piece and piece.lines) else self.arts.get("placeholder.txt")
        drawn_key = (key, size.width, size.height)
        text = "\n".join(art.display_fit(chosen, size.width, size.height)) if chosen else "[#9db0e0]no art[/]"
        self.app.call_from_thread(self._apply_preview, key, text, drawn_key)

    def _apply_preview(self, key, text, drawn_key):
        if key != self._current or not self.is_attached:
            return
        self.query_one("#art-preview", AsciiPanel).show_fitted(key, text, drawn_key)

    def _label(self, key, now):
        a = self.arts[key]
        star = "[#ffd75f]★[/] " if key == now else "  "
        nsfw = " [red]nsfw[/red]" if a.nsfw else ""
        src = " [cyan]yours[/cyan]" if a.source == "user" else ""
        return f"{star}{key}{src}{nsfw}"

    def _use(self, key):
        art.set_banner(key)
        for item in self.query_one("#art-menu", Menu).query(MenuItem):
            item.relabel(self._label(item.data, key))
        self._show(key)
        self.app.tell("home banner set", key)

    def action_pop(self):
        self.app.pop_screen()
