from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button

from ..widgets.footer import FooterHelp
from ..widgets.header import AppHeader
from .engine.scores import HighScores
from .games.breaker import BreakerGame
from .games.snake import SnakeGame
from .games.tetris import TetrisGame
from .games.twenty48 import Twenty48Game
from .screen import ArcadeScreen

GAMES = [TetrisGame, SnakeGame, BreakerGame, Twenty48Game]


class GamesScreen(Screen):
    TITLE = "ARCADE"
    COLS = 2
    BINDINGS = [
        Binding("escape", "pop", "back"),
        Binding("left", "move(-1, 0)", "left", show=False),
        Binding("right", "move(1, 0)", "right", show=False),
        Binding("up", "move(0, -1)", "up", show=False),
        Binding("down", "move(0, 1)", "down", show=False),
    ] + [Binding(str(i + 1), f"play({i})", f"game {i + 1}", show=False) for i in range(len(GAMES))]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scores = HighScores()

    def compose(self) -> ComposeResult:
        yield AppHeader("Arcade / mini-games", id="hdr")
        with Grid(id="games-grid"):
            for i, cls in enumerate(GAMES):
                yield Button(self._label(i, cls), id=f"g-{cls.KEY}")
        yield FooterHelp("arrows choose · enter plays · 1-4 or click too · esc back")

    def _label(self, i, cls):
        best = self.scores.get(cls.KEY)
        return f"[b]{i + 1}  {cls.TITLE}[/b]\n[#9db0e0]{cls.BLURB}[/]\n[#9db0e0]best {best}[/]"

    def on_mount(self):
        self.query_one(f"#g-{GAMES[0].KEY}", Button).focus()

    def _focused_index(self):
        for i, cls in enumerate(GAMES):
            if self.query_one(f"#g-{cls.KEY}", Button).has_focus:
                return i
        return 0

    def action_move(self, dx: int, dy: int):
        i = self._focused_index()
        col, row = i % self.COLS, i // self.COLS
        col, row = col + dx, row + dy
        j = row * self.COLS + col
        if 0 <= col < self.COLS and 0 <= j < len(GAMES):
            self.query_one(f"#g-{GAMES[j].KEY}", Button).focus()

    def on_screen_resume(self):
        for i, cls in enumerate(GAMES):
            self.query_one(f"#g-{cls.KEY}", Button).label = self._label(i, cls)

    @on(Button.Pressed)
    def _pick(self, ev):
        key = (ev.button.id or "").removeprefix("g-")
        for i, cls in enumerate(GAMES):
            if key == cls.KEY:
                self.action_play(i)
                return

    def action_play(self, index: int):
        self.app.push_screen(ArcadeScreen(GAMES[index], self.scores))

    def action_pop(self):
        self.app.pop_screen()
