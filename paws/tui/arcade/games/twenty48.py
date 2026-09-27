from __future__ import annotations

from ..engine.frame import Frame
from ..engine.game import Game
from ..engine.palette import PAL

SIZE = 4
_TILE_W, _TILE_H, _GAP = 3, 3, 1
_GOAL = 2048

_TILES = {
    2: ("#3a4a6a", "#e6ecff"),
    4: ("#3f5f8a", "#ffffff"),
    8: ("#5f87ff", "#101820"),
    16: ("#5fd7ff", "#101820"),
    32: ("#87d787", "#101820"),
    64: ("#d7d75f", "#101820"),
    128: ("#ffd75f", "#101820"),
    256: ("#ffaf5f", "#101820"),
    512: ("#ff875f", "#101820"),
    1024: ("#ff5f5f", "#ffffff"),
    2048: ("#ff87d7", "#101820"),
}
_BEYOND = ("#af87ff", "#ffffff")
_EMPTY_BG = "#1c2030"
_BOARD_BG = "#0e1018"

_VEC = {"left": (0, -1), "right": (0, 1), "up": (-1, 0), "down": (1, 0)}


def slide_line(line: list[int]) -> tuple[list[int], int, list[int]]:
    tiles = [v for v in line if v]
    out = []
    merged = []
    gained = 0
    i = 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] * 2)
            merged.append(len(out) - 1)
            gained += tiles[i] * 2
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (len(line) - len(out)), gained, merged


class Twenty48Game(Game):
    KEY = "2048"
    TITLE = "2048"
    BLURB = "slide, merge, think"
    HELP = "←↑↓→ or wasd slide the tiles"
    ROWS = _GAP + SIZE * (_TILE_H + _GAP)
    COLS = _GAP + SIZE * (_TILE_W + _GAP)

    def _start(self):
        self.grid = [[0] * SIZE for _ in range(SIZE)]
        self.moves = 0
        self.fresh: set[tuple[int, int]] = set()
        self.merged: set[tuple[int, int]] = set()
        self.reached = False
        self._spawn()
        self._spawn()

    def interval(self) -> float:
        return 0.1

    def _step(self):
        pass

    def _spawn(self):
        free = [(y, x) for y in range(SIZE) for x in range(SIZE) if not self.grid[y][x]]
        if not free:
            return
        y, x = self.rng.choice(free)
        self.grid[y][x] = 4 if self.rng.random() < 0.1 else 2
        self.fresh = {(y, x)}

    def best_tile(self) -> int:
        return max(max(row) for row in self.grid)

    def _lines(self, action):
        dy, dx = _VEC[action]
        order = range(SIZE)
        lines = []
        for k in range(SIZE):
            if dx:
                cols = order if dx < 0 else reversed(order)
                lines.append([(k, x) for x in cols])
            else:
                rows = order if dy < 0 else reversed(order)
                lines.append([(y, k) for y in rows])
        return lines

    def can_move(self) -> bool:
        for y in range(SIZE):
            for x in range(SIZE):
                v = self.grid[y][x]
                if not v:
                    return True
                if x + 1 < SIZE and self.grid[y][x + 1] == v:
                    return True
                if y + 1 < SIZE and self.grid[y + 1][x] == v:
                    return True
        return False

    def _press(self, action):
        if action not in _VEC:
            return
        changed, gained = False, 0
        merged = set()
        for coords in self._lines(action):
            before = [self.grid[y][x] for y, x in coords]
            after, pts, hits = slide_line(before)
            gained += pts
            merged.update(coords[i] for i in hits)
            if after != before:
                changed = True
                for (y, x), v in zip(coords, after):
                    self.grid[y][x] = v
        if not changed:
            return
        self.moves += 1
        self.merged = merged
        self.add_score(gained)
        self._spawn()
        top = self.best_tile()
        self.level = max(1, top.bit_length() - 1)
        if top >= _GOAL and not self.reached:
            self.reached = True
            self.won = True
            self.note = "2048! keep going for more"
        if not self.can_move():
            self.finish("no moves left" + (". you made 2048" if self.reached else ""), won=self.reached)

    def _origin(self, r, c):
        return _GAP + r * (_TILE_H + _GAP), _GAP + c * (_TILE_W + _GAP)

    def draw(self, f: Frame):
        f.clear(" " * f.cell_w, f"on {_BOARD_BG}")
        for r in range(SIZE):
            for c in range(SIZE):
                y0, x0 = self._origin(r, c)
                v = self.grid[r][c]
                bg, fg = _TILES.get(v, _BEYOND) if v else (_EMPTY_BG, PAL["grey"])
                bold = "bold " if (r, c) in self.merged else ""
                style = f"{bold}{fg} on {bg}"
                for dy in range(_TILE_H):
                    for dx in range(_TILE_W):
                        f.put(y0 + dy, x0 + dx, "  ", style)
                label = str(v) if v else "·"
                width = _TILE_W * f.cell_w
                text = label.center(width)
                mid = y0 + _TILE_H // 2
                for dx in range(_TILE_W):
                    f.put(mid, x0 + dx, text[dx * 2 : dx * 2 + 2], style)
                if (r, c) in self.fresh:
                    f.put(y0 + _TILE_H - 1, x0 + _TILE_W // 2, "▔▔", f"{fg} on {bg}")

    def stats(self) -> list[tuple[str, str]]:
        return [("biggest", str(self.best_tile())), ("moves", str(self.moves))]
