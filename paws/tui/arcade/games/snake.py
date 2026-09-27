from __future__ import annotations

from collections import deque

from ..engine.frame import Frame
from ..engine.game import Game
from ..engine.palette import BLOCK, PAL

_DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


_START_LEN = 4


class SnakeGame(Game):
    KEY = "snake"
    TITLE = "SNAKE"
    BLURB = "eat, grow, survive"
    HELP = "←↑↓→ or wasd to steer"
    ROWS, COLS = 16, 28

    def _start(self):
        cy, cx = self.ROWS // 2, self.COLS // 2
        self.seg: deque[tuple[int, int]] = deque((cy, cx - i) for i in range(_START_LEN))
        self.dir = (0, 1)
        self.turns: deque[tuple[int, int]] = deque()
        self.food = self._place_food()
        self.eaten = 0

    def _place_food(self):
        free = [(y, x) for y in range(self.ROWS) for x in range(self.COLS) if (y, x) not in self.seg]
        return self.rng.choice(free) if free else (-1, -1)

    def interval(self) -> float:
        return max(0.06, 0.15 - 0.003 * (len(self.seg) - _START_LEN))

    def _press(self, action):
        d = _DIRS.get(action)
        if d is None or len(self.turns) >= 2:
            return
        last = self.turns[-1] if self.turns else self.dir
        if d != last and d != (-last[0], -last[1]):
            self.turns.append(d)

    def _step(self):
        if self.turns:
            self.dir = self.turns.popleft()
        hy, hx = self.seg[0]
        ny, nx = hy + self.dir[0], hx + self.dir[1]
        if not (0 <= ny < self.ROWS and 0 <= nx < self.COLS):
            return self.finish("you hit the wall")
        eating = (ny, nx) == self.food
        body = list(self.seg) if eating else list(self.seg)[:-1]
        if (ny, nx) in body:
            return self.finish("you bit yourself")
        self.seg.appendleft((ny, nx))
        if eating:
            self.eaten += 1
            self.add_score(10)
            self.level = self.eaten // 5 + 1
            if len(self.seg) >= self.ROWS * self.COLS:
                return self.finish("the whole board is snake. you win", won=True)
            self.food = self._place_food()
        else:
            self.seg.pop()

    def draw(self, f: Frame):
        if self.food != (-1, -1):
            f.put(*self.food, "()", f"bold {PAL['red']}")
        for i, (y, x) in enumerate(self.seg):
            f.put(y, x, BLOCK, PAL["cyan"] if i == 0 else (PAL["green"] if i % 2 else "#6cbf6c"))

    def stats(self) -> list[tuple[str, str]]:
        return [("length", str(len(self.seg)))]
