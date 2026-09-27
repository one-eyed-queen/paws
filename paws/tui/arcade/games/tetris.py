from __future__ import annotations

from rich.text import Text

from ..engine.frame import Frame
from ..engine.game import Game
from ..engine.palette import BLOCK, EMPTY, PAL

_SHAPES = {
    "I": ["....", "XXXX", "....", "...."],
    "O": ["XX", "XX"],
    "T": [".X.", "XXX", "..."],
    "S": [".XX", "XX.", "..."],
    "Z": ["XX.", ".XX", "..."],
    "J": ["X..", "XXX", "..."],
    "L": ["..X", "XXX", "..."],
}


COLORS = {
    "I": PAL["cyan"],
    "O": PAL["yellow"],
    "T": PAL["purple"],
    "S": PAL["green"],
    "Z": PAL["red"],
    "J": PAL["blue"],
    "L": PAL["orange"],
}


_LINE_SCORE = (0, 100, 300, 500, 800)


def _cells(rows):
    return [(r, c) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "X"]


def _build_rotations():
    out = {}
    for kind, rows in _SHAPES.items():
        n = len(rows)
        current_shape = _cells(rows)
        states = [current_shape]
        for _ in range(3):
            current_shape = sorted((c, n - 1 - r) for r, c in current_shape)
            if current_shape == sorted(states[0]):
                break
            states.append(current_shape)
        out[kind] = states if kind != "O" else [states[0]]
    return out


ROTS = _build_rotations()


class TetrisGame(Game):
    KEY = "tetris"
    TITLE = "TETRIS"
    BLURB = "stack, clear lines"
    HELP = "←→ move   ↑ rotate   z rotate back   ↓ soft drop   space hard drop   c hold"
    ROWS, COLS = 20, 10

    def _start(self):
        self.grid: list[list[str | None]] = [[None] * self.COLS for _ in range(self.ROWS)]
        self.lines = 0
        self.held: str | None = None
        self.can_hold = True
        self.grounded = 0
        self.resets = 0
        self.bag: list[str] = []
        self.queue = [self._draw_piece() for _ in range(3)]
        self._spawn()

    def _draw_piece(self):
        if not self.bag:
            self.bag = list(_SHAPES)
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _spawn(self, kind=None):
        if kind is None:
            self.kind = self.queue.pop(0)
            self.queue.append(self._draw_piece())
            self.can_hold = True
        else:
            self.kind = kind
        self.grounded = self.resets = 0
        self.rot = 0
        cells = ROTS[self.kind][0]
        n = len(_SHAPES[self.kind])
        self.y = -min(r for r, _ in cells)
        self.x = (self.COLS - n) // 2
        if self._collides(self.kind, self.rot, self.y, self.x):
            self.finish("the stack reached the top")

    def _collides(self, kind, rot, y, x):
        for r, c in ROTS[kind][rot]:
            yy, xx = y + r, x + c
            if xx < 0 or xx >= self.COLS or yy >= self.ROWS:
                return True
            if yy >= 0 and self.grid[yy][xx] is not None:
                return True
        return False

    def _move(self, dy, dx):
        if self._collides(self.kind, self.rot, self.y + dy, self.x + dx):
            return False
        self.y += dy
        self.x += dx
        self._slid()
        return True

    def _slid(self):
        if self.grounded and self.resets < 12:
            self.grounded = 0
            self.resets += 1

    def _rotate(self, d):
        if self.kind == "O":
            return
        new = (self.rot + d) % len(ROTS[self.kind])
        for dy, dx in ((0, 0), (0, -1), (0, 1), (0, -2), (0, 2), (-1, 0), (-1, -1), (-1, 1)):
            if not self._collides(self.kind, new, self.y + dy, self.x + dx):
                self.rot, self.y, self.x = new, self.y + dy, self.x + dx
                self._slid()
                return

    def _ghost_y(self):
        y = self.y
        while not self._collides(self.kind, self.rot, y + 1, self.x):
            y += 1
        return y

    def _lock(self):
        for r, c in ROTS[self.kind][self.rot]:
            yy, xx = self.y + r, self.x + c
            if 0 <= yy < self.ROWS:
                self.grid[yy][xx] = self.kind
        kept = [row for row in self.grid if any(cell is None for cell in row)]
        cleared = self.ROWS - len(kept)
        if cleared:
            self.grid = [[None] * self.COLS for _ in range(cleared)] + kept
            self.lines += cleared
            self.add_score(_LINE_SCORE[cleared] * self.level)
            self.level = self.lines // 10 + 1
        self._spawn()

    def interval(self) -> float:
        return max(0.07, 0.55 * 0.85 ** (self.level - 1))

    def _lock_delay(self):
        return max(1, round(0.4 / self.interval()))

    def _step(self):
        if self._collides(self.kind, self.rot, self.y + 1, self.x):
            self.grounded += 1
            if self.grounded > self._lock_delay():
                self._lock()
            return
        self.y += 1
        self.grounded = 0

    def _hold(self):
        if not self.can_hold:
            return
        current = self.kind
        if self.held is None:
            self.held = current
            self._spawn()
        else:
            self.held, swap = current, self.held
            self._spawn(swap)
        self.can_hold = False

    def _press(self, action):
        if action == "left":
            self._move(0, -1)
        elif action == "right":
            self._move(0, 1)
        elif action == "up":
            self._rotate(1)
        elif action == "rotate_back":
            self._rotate(-1)
        elif action == "down":
            if self._move(1, 0):
                self.add_score(1)
        elif action == "hold":
            self._hold()
        elif action in ("fire", "drop"):
            while self._move(1, 0):
                self.add_score(2)
            self._lock()

    def draw(self, f: Frame):
        for y in range(self.ROWS):
            for x in range(self.COLS):
                kind = self.grid[y][x]
                if kind:
                    f.put(y, x, BLOCK, COLORS[kind])
                else:
                    f.put(y, x, " .", PAL["faint"])
        if self.over and not self.won:
            return
        color = COLORS[self.kind]
        gy = self._ghost_y()
        for r, c in ROTS[self.kind][self.rot]:
            if 0 <= gy + r < self.ROWS and self.grid[gy + r][self.x + c] is None:
                f.put(gy + r, self.x + c, "░░", color)
        for r, c in ROTS[self.kind][self.rot]:
            f.put(self.y + r, self.x + c, BLOCK, color)

    def stats(self) -> list[tuple[str, str]]:
        return [("level", str(self.level)), ("lines", str(self.lines))]

    @staticmethod
    def _mini(t, kind):
        rows = _SHAPES[kind]
        for r in range(len(rows)):
            if "X" not in rows[r]:
                continue
            for ch in rows[r]:
                t.append(BLOCK if ch == "X" else EMPTY, COLORS[kind] if ch == "X" else None)
            t.append("\n")
        t.append("\n")

    def side(self) -> Text:
        t = Text(no_wrap=True)
        t.append("hold" + ("" if self.can_hold else " (used)") + "\n", PAL["grey"])
        if self.held:
            self._mini(t, self.held)
        else:
            t.append("-\n\n", PAL["faint"])
        t.append("next\n", PAL["grey"])
        for kind in self.queue[:3]:
            self._mini(t, kind)
        return t
