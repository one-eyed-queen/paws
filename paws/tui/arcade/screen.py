from __future__ import annotations

import re
import time

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from .engine.game import Game
from .engine.palette import PAL
from .engine.panel import label
from .engine.scores import HighScores

FPS = 30


_MAX_CATCHUP = 6


SIDE_W = 32


KEYMAP = {
    "left": "left",
    "a": "left",
    "h": "left",
    "right": "right",
    "d": "right",
    "l": "right",
    "up": "up",
    "w": "up",
    "k": "up",
    "down": "down",
    "s": "down",
    "j": "down",
    "space": "fire",
    "enter": "fire",
    "z": "rotate_back",
    "c": "hold",
}


class ArcadeScreen(Screen):
    no_screen_picture = True

    BINDINGS = [
        Binding("escape", "back", "back"),
        Binding("q", "back", "back", show=False),
        Binding("p", "pause", "pause"),
        Binding("r", "restart", "restart"),
    ]

    def __init__(self, game_cls: type[Game], scores: HighScores | None = None, **kwargs):
        super().__init__(**kwargs)
        self.game_cls = game_cls
        self.scores = scores or HighScores()
        self.game: Game | None = None
        self.paused = False
        self.too_small = False
        self.record = False
        self._recorded = False
        self._acc = 0.0
        self._last = time.monotonic()
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="game-box"):
            yield Static("", id="game-title")
            with Horizontal(id="game-row"):
                yield Static("", id="game-canvas")
                with Vertical(id="game-side"):
                    yield Static("", id="game-info")
                    yield Static("", id="game-next")
                    yield Static("", id="game-help")
            yield Static("", id="game-msg")

    def on_mount(self):
        self.game = self.game_cls(best=self.scores.get(self.game_cls.KEY))
        self._last = time.monotonic()
        self._timer = self.set_interval(1 / FPS, self._frame)
        self._layout()
        self._paint()

    def on_unmount(self):
        if self._timer is not None:
            self._timer.stop()
        self._save()

    def on_screen_suspend(self):
        self.paused = True

    def on_resize(self, event: events.Resize):
        self._layout()
        self._paint()

    def _need(self):
        g = self.game
        return g.COLS * 2 + 2, g.ROWS + 5

    def _layout(self):
        if self.game is None:
            return
        need_w, need_h = self._need()
        w, h = self.size.width, self.size.height
        self.too_small = bool(w and h) and (w < need_w or h < need_h)
        self.query_one("#game-side").display = w >= need_w + SIDE_W + 2
        self.query_one("#game-row").display = not self.too_small

    def _frame(self):
        g = self.game
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if g is None:
            return
        if self.paused or self.too_small or g.over:
            self._acc = 0.0
        else:
            self._acc += min(dt, 0.25)
            n = 0
            while self._acc >= g.interval() and n < _MAX_CATCHUP and not g.over:
                self._acc -= g.interval()
                g.step()
                n += 1
            if n >= _MAX_CATCHUP:
                self._acc = 0.0
        if g.over and not self._recorded:
            self._save()
        if g.dirty:
            self._paint()

    def _save(self):
        g = self.game
        if g is None or self._recorded and not g.over:
            return
        if g.score > 0:
            self.record = self.scores.submit(g.KEY, g.score) or self.record
        self._recorded = g.over

    def on_key(self, event: events.Key):
        if self.game is not None and self.game.over and event.key in ("enter", "space"):
            event.stop()
            self.action_restart()
            return
        action = KEYMAP.get(event.key)
        if action is None or self.game is None:
            return
        event.stop()
        if self.paused or self.too_small:
            return
        self.game.press(action)
        if self.game.dirty:
            self._paint()

    def action_pause(self):
        if self.game is None or self.game.over:
            return
        self.paused = not self.paused
        self._last = time.monotonic()
        self._paint()

    def action_restart(self):
        if self.game is None:
            return
        self._save()
        self.game.reset()
        self.paused = False
        self.record = False
        self._recorded = False
        self._acc = 0.0
        self._last = time.monotonic()
        self._paint()

    def action_back(self):
        self._save()
        self.app.pop_screen()

    def on_screen_resume(self):
        self._last = time.monotonic()

    def _message(self):
        g = self.game
        t = Text(justify="center")
        if self.too_small:
            need_w, need_h = self._need()
            t.append(
                f"window too small for {g.TITLE}: need {need_w}x{need_h}, have {self.size.width}x{self.size.height}",
                PAL["orange"],
            )
        elif g.over:
            t.append(g.note or "game over", f"bold {PAL['green'] if g.won else PAL['red']}")
            if self.record:
                t.append("   new record!", f"bold {PAL['yellow']}")
            t.append("   enter or r to play again · esc back", PAL["grey"])
        elif self.paused:
            t.append("paused   p to resume", f"bold {PAL['yellow']}")
        elif g.note:
            t.append(g.note, f"bold {PAL['cyan']}")
        else:
            t.append("p pause · r restart · esc back", PAL["grey"])
        return t

    def _paint(self):
        g = self.game
        if g is None:
            return
        title = Text(no_wrap=True)
        title.append(g.TITLE, f"bold {PAL['white']}")
        title.append(f"   score {g.score}", PAL["cyan"])
        title.append(f"   best {max(g.best, g.score)}", PAL["grey"])
        self.query_one("#game-title", Static).update(title)
        if not self.too_small:
            self.query_one("#game-canvas", Static).update(g.frame().text())
        else:
            g.dirty = False

        info = Text()
        rows = [("score", g.score), ("best", max(g.best, g.score)), *g.stats()]
        for i, (name, value) in enumerate(rows):
            info.append_text(label(name, value))
            if i < len(rows) - 1:
                info.append("\n")
        self.query_one("#game-info", Static).update(info)
        side = g.side()
        self.query_one("#game-next", Static).update(side if side is not None else "")
        keys = [part.strip() for part in re.split(r"\s{3,}", g.HELP) if part.strip()]
        self.query_one("#game-help", Static).update(
            Text("\n".join(keys + ["", "p pause", "r restart", "esc back"]), PAL["grey"])
        )
        self.query_one("#game-msg", Static).update(self._message())
