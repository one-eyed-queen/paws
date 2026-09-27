from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from textual.containers import Container
from textual.widgets import Static

from ... import __version__, settings
from ...paths import DATA_DIR
from .backdrop import RGB, Backdrop

BANNER = DATA_DIR / "img" / "paws-banner.png"
BASE: RGB = (12, 20, 36)


def _on_bar(banner, base=BASE):
    from PIL import Image, ImageChops

    rgba = banner.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 255:
        canvas = Image.new("RGB", rgba.size, base)
        canvas.paste(rgba.convert("RGB"), (0, 0), alpha)
        return canvas
    return ImageChops.screen(rgba.convert("RGB"), Image.new("RGB", rgba.size, base))


class HeaderBackdrop(Backdrop):
    def __init__(self, banner: Path, base: RGB = BASE):
        super().__init__(banner, base=base, strength=1.0)

    def _build(self, w, h):
        from PIL import Image

        canvas = Image.new("RGB", (w, h), self.base)
        banner = self._src.convert("RGBA")
        bw = min(w, round(banner.width * h / banner.height))
        canvas.paste(_on_bar(banner.resize((bw, h), Image.LANCZOS), self.base), (0, 0))
        return canvas


def _text(title):
    version = f"[#9db0e0]v{__version__}[/]"
    if title is None:
        return f"[b]{version}[/b]  "
    return f"[b]{version}  [#9db0e0]·[/]  [#00d0ff]▸ {title}[/][/b]  "


def _plain_text(title):
    text = f"[b #00d0ff]PAWS[/] [#9db0e0]v{__version__}  ·  manager for[/] [#ff9d3d]SLSsteam[/]"
    return text if title is None else f"{text}  [#9db0e0]·[/]  [b #00d0ff]{title}[/]"


def hires_banner(path: Path | None = None):
    return _hires_banner(str(path or BANNER))


@lru_cache(maxsize=2)
def _hires_banner(path):
    from PIL import Image

    return _on_bar(Image.open(path))


BANNER_RATIO = 640 / 89
TEXT_ROOM = 10


def contain(image, cols: int, rows: int, cw: float, ch: float, base: RGB = BASE, anchor: str = "left"):
    from PIL import Image

    width, height = max(1, round(cols * cw)), max(1, round(rows * ch))
    k = min(width / image.width, height / image.height)
    w, h = max(1, round(image.width * k)), max(1, round(image.height * k))
    canvas = Image.new("RGB", (width, height), base)
    x = 0 if anchor == "left" else (width - w) // 2
    canvas.paste(image.convert("RGB").resize((w, h), Image.LANCZOS), (x, (height - h) // 2))
    return canvas


@lru_cache(maxsize=16)
def _boxed(cols, rows, cw, ch):
    return contain(_hires_banner(str(BANNER)), cols, rows, cw, ch, anchor="left")


class PaintedHeader(Static):
    def __init__(self, title: str | None = None, **kwargs):
        super().__init__(markup=True, **kwargs)
        self._title = title

    def on_mount(self):
        self.update(_text(self._title))
        self._use_picture()

    backdrop: HeaderBackdrop | None = None

    def _use_picture(self):
        if not BANNER.exists():
            self.backdrop = None
            return
        bd = HeaderBackdrop(BANNER)
        self.backdrop = bd if bd.load() else None
        self.refresh()


class AppHeader(Container):
    def __init__(self, title: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self.set_class(title is None, "-home")
        self._banner = None

    def compose(self):
        from . import hires

        if settings.is_minimal():
            yield Static(_plain_text(self._title), id="hdr-text", markup=True)
            return
        if not hires.available() or not BANNER.exists():
            yield PaintedHeader(self._title)
            return
        self._banner = hires.picture(hires_banner(), id="hdr-banner")
        yield self._banner
        yield Static(_text(self._title), id="hdr-text", markup=True)

    def on_resize(self, event):
        self._fit_banner()

    def _fit_banner(self):
        from . import hires

        if self._banner is None or not self.size.width or not self.size.height:
            return
        cw, ch = hires.cell()
        for rows in range(self.size.height, 0, -1):
            cols = max(1, round(rows * ch * BANNER_RATIO / cw))
            if cols <= self.size.width - TEXT_ROOM:
                key = (cols, rows, round(cw, 2), round(ch, 2))
                self._banner.styles.width = cols
                self._banner.styles.height = rows
                if getattr(self._banner, "_fitted", None) != key:
                    self._banner._fitted = key
                    self._banner.image = _boxed(cols, rows, round(cw, 2), round(ch, 2))
                self._banner.display = True
                return
        self._banner.display = False
