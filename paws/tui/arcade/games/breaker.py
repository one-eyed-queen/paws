from __future__ import annotations

import math

from ..engine.frame import Frame
from ..engine.game import Game
from ..engine.palette import PAL

_BRICK_W = 2


_BRICK_ROWS = 6


_ROW_COLORS = (PAL["red"], PAL["orange"], PAL["yellow"], PAL["green"], PAL["cyan"], PAL["purple"])


_PADDLE_W = 5


_MAX_ANGLE = math.radians(58)


class BreakerGame(Game):
    KEY = "breaker"
    TITLE = "BRICK BREAKER"
    BLURB = "keep the ball alive"
    HELP = "←→ or a/d move   space launch"
    ROWS, COLS = 20, 20

    def _start(self):
        self.lives = 3
        self.px = (self.COLS - _PADDLE_W) // 2
        self.py = self.ROWS - 2
        self._build_wall()
        self._serve()

    def _build_wall(self):
        self.bricks: dict[tuple[int, int], int] = {
            (2 + r, c): r for r in range(_BRICK_ROWS) for c in range(self.COLS // _BRICK_W)
        }
        self.total = len(self.bricks)

    def _speed(self):
        cleared = self.total - len(self.bricks)
        return min(0.75, 0.42 + 0.03 * (self.level - 1) + 0.004 * cleared)

    def _serve(self):
        self.serving = True
        self.bx = self.px + _PADDLE_W / 2
        self.by = self.py - 0.01
        self.vx = self.vy = 0.0
        self.note = "space to launch"

    def interval(self) -> float:
        return 0.03

    def _press(self, action):
        if action in ("left", "right"):
            self.px = max(0, min(self.COLS - _PADDLE_W, self.px + (-2 if action == "left" else 2)))
            if self.serving:
                self.bx = self.px + _PADDLE_W / 2
        elif action in ("fire", "up") and self.serving:
            self.serving = False
            self.note = ""
            a = self.rng.uniform(-0.35, 0.35)
            s = self._speed()
            self.vx, self.vy = s * math.sin(a), -s * math.cos(a)

    def _step(self):
        if self.serving:
            return
        n = max(1, math.ceil(max(abs(self.vx), abs(self.vy)) / 0.35))
        for _ in range(n):
            self._advance(self.vx / n, self.vy / n)
            if self.over or self.serving:
                return

    def _advance(self, dx, dy):
        ox, oy = self.bx, self.by
        nx, ny = ox + dx, oy + dy
        if nx < 0:
            nx, self.vx = -nx, abs(self.vx)
        elif nx >= self.COLS:
            nx, self.vx = 2 * self.COLS - nx - 1e-6, -abs(self.vx)
        if ny < 0:
            ny, self.vy = -ny, abs(self.vy)

        cell = (int(ny), int(nx) // _BRICK_W)
        if cell in self.bricks:
            row = self.bricks.pop(cell)
            self.add_score(10 * (_BRICK_ROWS - row) * self.level)
            crossed_x = int(nx) != int(ox)
            crossed_y = int(ny) != int(oy)
            if crossed_x and not crossed_y:
                self.vx = -self.vx
            elif crossed_y and not crossed_x:
                self.vy = -self.vy
            else:
                self.vx, self.vy = -self.vx, -self.vy
            self._retarget()
            if not self.bricks:
                self.level += 1
                self._build_wall()
                self._serve()
            return None

        if self.vy > 0 and oy < self.py <= ny and self.px - 0.3 <= nx <= self.px + _PADDLE_W + 0.3:
            hit = (nx - (self.px + _PADDLE_W / 2)) / (_PADDLE_W / 2)
            a = max(-1.0, min(1.0, hit)) * _MAX_ANGLE
            s = self._speed()
            self.vx, self.vy = s * math.sin(a), -s * math.cos(a)
            self.bx, self.by = nx, self.py - 0.01
            return None

        if ny >= self.ROWS:
            self.lives -= 1
            if self.lives <= 0:
                self.by = self.ROWS - 1
                return self.finish("the ball got away")
            self._serve()
            return None
        self.bx, self.by = nx, ny

    def _retarget(self):
        current_speed = math.hypot(self.vx, self.vy)
        if current_speed:
            k = self._speed() / current_speed
            self.vx, self.vy = self.vx * k, self.vy * k

    def draw(self, f: Frame):
        for (y, c), row in self.bricks.items():
            style = _ROW_COLORS[row % len(_ROW_COLORS)]
            f.put(y, c * _BRICK_W, "▐█", style)
            f.put(y, c * _BRICK_W + 1, "█▌", style)
        for k in range(_PADDLE_W):
            f.put(self.py, self.px + k, "▀▀", PAL["white"])
        if not (self.over and not self.won):
            f.put(int(self.by), int(self.bx), "()", f"bold {PAL['yellow']}")

    def stats(self) -> list[tuple[str, str]]:
        return [
            ("lives", "♥ " * self.lives if self.lives else "-"),
            ("level", str(self.level)),
            ("bricks", str(len(self.bricks))),
        ]
