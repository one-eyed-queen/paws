from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

from rich.cells import cell_len
from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip

from ... import settings
from ...paths import DATA_DIR

BG_IMAGE = DATA_DIR / "img" / "paws-bg.png"
STRENGTH = 0.3
SCREEN_STRENGTH = 0.12
SHARPEN = 60
SCREEN_BLUR = 1.4

UNDERLAY = False

RGB = tuple[int, int, int]


@lru_cache(maxsize=None)
def load_image(path: Path):
    try:
        from PIL import Image

        return Image.open(path).convert("RGB")
    except Exception:
        return None


class Backdrop:
    def __init__(
        self,
        path: Path = BG_IMAGE,
        base: RGB = (16, 26, 48),
        strength: float = STRENGTH,
        blur: float = 0.0,
    ):
        self.path = path
        self.blur = blur
        self.sharpen = SHARPEN if not blur else 0
        self.base = base
        self.strength = strength
        self._src = None
        self._size: tuple[int, int] | None = None
        self._px: list[list[RGB]] = []

    def load(self) -> bool:
        if settings.is_minimal():
            return False
        self._src = load_image(self.path)
        return self._src is not None

    def _build(self, w, h):
        from PIL import Image

        iw, ih = self._src.size
        scale = max(w / iw, h / ih)
        big = self._src.resize((max(w, round(iw * scale)), max(h, round(ih * scale))), Image.LANCZOS)
        left, top = (big.width - w) // 2, (big.height - h) // 2
        return big.crop((left, top, left + w, top + h))

    def _prepare(self, cols, rows):
        w, h = max(1, cols), max(1, rows * 2)
        image = self._build(w, h)
        from PIL import ImageFilter

        if self.blur:
            image = image.filter(ImageFilter.GaussianBlur(self.blur))
        elif self.sharpen:
            image = image.filter(ImageFilter.UnsharpMask(radius=0.9, percent=self.sharpen, threshold=2))
        px = image.load()
        b, s = self.base, self.strength
        self._px = [
            [tuple(round(b[i] + (px[x, y][i] - b[i]) * s) for i in range(3)) for x in range(w)] for y in range(h)
        ]
        self._size = (cols, rows)

    def pixels(self, x: int, y: int, cols: int, rows: int) -> tuple[RGB, RGB] | None:
        if self._src is None or cols <= 0 or rows <= 0:
            return None
        if self._size != (cols, rows):
            self._prepare(cols, rows)
        if not (0 <= x < cols and 0 <= y < rows):
            return None
        return self._px[y * 2][x], self._px[y * 2 + 1][x]


@lru_cache(maxsize=32768)
def _blank_segment(px):
    (r1, g1, b1), (r2, g2, b2) = px
    return Segment("▀", Style(color=Color.from_rgb(r1, g1, b1), bgcolor=Color.from_rgb(r2, g2, b2)))


TEXT_BACKING = 0.55


@lru_cache(maxsize=32768)
def _tint(px):
    r, g, b = (int((a + c) // 2 * TEXT_BACKING) for a, c in zip(*px))
    return Style(bgcolor=Color.from_rgb(r, g, b))


@lru_cache(maxsize=4096)
def _shows(style, base):
    if style is None or style.bgcolor is None:
        return False
    return tuple(style.bgcolor.get_truecolor()) == base


_MEMO: dict[tuple, tuple[Strip, Strip]] = {}


def paint(
    strips: list[Strip],
    backdrop: Backdrop,
    base: RGB,
    x0: int,
    y0: int,
    cols: int,
    rows: int,
) -> list[Strip]:
    out = []
    for i, strip in enumerate(strips):
        key = (id(strip), id(backdrop), base, x0, y0 + i, cols, rows)
        hit = _MEMO.get(key)
        if hit is not None and hit[0] is strip:
            out.append(hit[1])
            continue
        painted = _paint_strip(strip, backdrop, base, x0, y0 + i, cols, rows)
        if len(_MEMO) > 6000:
            _MEMO.clear()
        _MEMO[key] = (strip, painted)
        out.append(painted)
    return out


def _paint_strip(strip, backdrop, base, x0, y, cols, rows):
    segs = []
    has_text = bool(strip.text.strip())
    x = x0
    for seg in strip:
        style = seg.style
        if seg.control or not _shows(style, base):
            segs.append(seg)
            x += 0 if seg.control else cell_len(seg.text)
            continue
        for ch in seg.text:
            px = backdrop.pixels(x, y, cols, rows)
            width = cell_len(ch)
            if px is None or width == 0:
                segs.append(Segment(ch, style))
            elif ch == " " and not has_text:
                segs.append(_blank_segment(px))
            else:
                segs.append(Segment(ch, (style or Style()) + _tint(px)))
            x += width
    return Strip(segs, strip.cell_length)


def panel_backdrop(widget, strength: float = STRENGTH, path: Path = BG_IMAGE, blur: float = 0.0) -> Backdrop | None:
    bd = Backdrop(path, base=tuple(widget.background_colors[1].rgb), strength=strength, blur=blur)
    return bd if bd.load() else None


def _clear_segment(seg):
    return Segment(seg.text, (seg.style or Style()) + _DEFAULT_BG, seg.control)


_DEFAULT_BG = Style(bgcolor=Color.default())
_CLEAR_MEMO: dict[tuple, tuple[Strip, Strip]] = {}


def clear_plain(strips: list[Strip], base: RGB) -> list[Strip]:
    out = []
    for strip in strips:
        key = (id(strip), base)
        hit = _CLEAR_MEMO.get(key)
        if hit is not None and hit[0] is strip:
            out.append(hit[1])
            continue
        cleared = Strip(
            [_clear_segment(s) if not s.control and _shows(s.style, base) else s for s in strip],
            strip.cell_length,
        )
        if len(_CLEAR_MEMO) > 6000:
            _CLEAR_MEMO.clear()
        _CLEAR_MEMO[key] = (strip, cleared)
        out.append(cleared)
    return out


def _owner(widget):
    from textual.screen import ModalScreen, Screen

    try:
        bare_screen = bool(getattr(widget.screen, "no_screen_picture", False))
    except Exception:
        bare_screen = False
    for w in widget.ancestors_with_self:
        if getattr(w, "backdrop_off", False):
            return None
        if getattr(w, "backdrop", None) is not None:
            return w
        if bare_screen:
            continue
        if isinstance(w, Screen):
            if isinstance(w, ModalScreen):
                return None
            if UNDERLAY:
                return w
            if not getattr(w, "_screen_backdrop_tried", False):
                w._screen_backdrop_tried = True
                w.backdrop = panel_backdrop(w, SCREEN_STRENGTH, blur=SCREEN_BLUR)
            return w if w.backdrop is not None else None
    return None


def _base_rgb(owner):
    now = time.monotonic()
    kept = getattr(owner, "_base_rgb", None)
    if kept is not None and now - kept[0] < 2.0:
        return kept[1]
    rgb = tuple(owner.background_colors[1].rgb)
    owner._base_rgb = (now, rgb)
    return rgb


_original = None


def install():
    global _original
    from textual.widget import Widget

    if _original is not None:
        return
    _original = Widget.render_lines

    def render_lines(self, crop):
        strips = _original(self, crop)
        try:
            owner = _owner(self)
            if owner is None:
                return strips
            base = _base_rgb(owner)
            if UNDERLAY and getattr(owner, "backdrop", None) is None:
                return clear_plain(strips, base)
            pr, wr = owner.region, self.region
            return paint(
                strips,
                owner.backdrop,
                base,
                wr.x - pr.x + crop.x,
                wr.y - pr.y + crop.y,
                pr.width,
                pr.height,
            )
        except Exception:
            return strips

    Widget.render_lines = render_lines
