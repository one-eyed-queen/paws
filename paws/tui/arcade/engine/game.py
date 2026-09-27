from __future__ import annotations

import random

from rich.text import Text

from .frame import Frame


class Game:
    KEY = "game"
    TITLE = "GAME"
    BLURB = ""
    HELP = ""
    ROWS = 20
    COLS = 10

    def __init__(self, rng: random.Random | None = None, best: int = 0):
        self.rng = rng or random.Random()
        self.best = best
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.over = False
        self.won = False
        self.steps = 0
        self.note = ""
        self.dirty = True
        self._start()

    def finish(self, message: str, won: bool = False):
        self.over = True
        self.won = won
        self.note = message
        self.best = max(self.best, self.score)

    def _start(self):
        raise NotImplementedError

    def _step(self):
        raise NotImplementedError

    def _press(self, action):
        raise NotImplementedError

    def interval(self) -> float:
        raise NotImplementedError

    def draw(self, f: Frame):
        raise NotImplementedError

    def stats(self) -> list[tuple[str, str]]:
        return []

    def side(self) -> Text | None:
        return None

    def step(self):
        if self.over:
            return
        self.steps += 1
        self._step()
        self.dirty = True

    def press(self, action: str):
        if self.over:
            return
        self._press(action)
        self.dirty = True

    def frame(self) -> Frame:
        f = Frame(self.ROWS, self.COLS)
        self.draw(f)
        self.dirty = False
        return f

    def add_score(self, n: int):
        self.score += n
        self.best = max(self.best, self.score)
