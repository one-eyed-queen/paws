from __future__ import annotations

from rich.text import Text


class Frame:
    def __init__(self, rows: int, cols: int, cell_w: int = 2):
        self.rows, self.cols, self.cell_w = rows, cols, cell_w
        self.clear()

    def clear(self, glyph: str | None = None, style: str = ""):
        g = glyph if glyph is not None else " " * self.cell_w
        self._g = [[(g, style) for _ in range(self.cols)] for _ in range(self.rows)]

    def put(self, y: int, x: int, glyph: str, style: str = ""):
        if 0 <= y < self.rows and 0 <= x < self.cols:
            self._g[y][x] = (glyph[: self.cell_w].ljust(self.cell_w), style)

    def get(self, y: int, x: int) -> tuple[str, str]:
        if 0 <= y < self.rows and 0 <= x < self.cols:
            return self._g[y][x]
        return (" " * self.cell_w, "")

    def plain(self) -> list[str]:
        return ["".join(g for g, _ in row) for row in self._g]

    def text(self) -> Text:
        out = Text(no_wrap=True, overflow="crop")
        for y, row in enumerate(self._g):
            run, run_style = "", None
            for g, style in row:
                style = style or None
                if style == run_style:
                    run += g
                    continue
                if run:
                    out.append(run, run_style)
                run, run_style = g, style
            if run:
                out.append(run, run_style)
            if y < self.rows - 1:
                out.append("\n")
        return out
