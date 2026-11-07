from __future__ import annotations

from textual.message import Message
from textual.widgets import Static


def spacing_text(info, sizes: bool = True) -> str:
    """zoom, char spacing and line spacing of a drawn piece of art. the spacing is the terminal's cell: one braille
    character (2x4 dots) per cell, so that's the gap between characters and between lines on screen"""
    from .hires import cell

    w, h, shown_w, shown_h, zoom = info
    cw, ch = cell()
    size = f"{w}x{h}" if (w, h) == (shown_w, shown_h) else f"{w}x{h} → {shown_w}x{shown_h}"
    zoomed = f"zoom {round(zoom * 100)}%" + (f" ({size})" if sizes else "")
    return f"{zoomed} · char space {round(cw)}px · line space {round(ch)}px"


class AsciiPanel(Static):
    class Drawn(Message):
        """the art was (re)drawn: a new piece, or the same one at a new size"""

        def __init__(self, panel: "AsciiPanel"):
            super().__init__()
            self.panel = panel

    def __init__(self, art_name: str | None = None, **kwargs):
        super().__init__(markup=True, **kwargs)
        self._art_name: str | None = None
        self._drawn: tuple | None = None
        self.info: tuple[int, int, int, int, float] | None = None
        if art_name:
            self.show(art_name)

    def spacing(self, sizes: bool = True) -> str:
        return spacing_text(self.info, sizes) if self.info and self.info[0] else ""

    def pending(self, name: str, art=None):
        self._art_name = name
        self._art = art
        self._drawn = None

    def show(self, name: str | None = None, art=None) -> bool:
        from ... import art as art_module

        self._art_name = name or art_module.banner_name()
        self._art = art
        self._drawn = None
        return self._draw()

    def show_fitted(self, name: str, text: str, key: tuple, info=None):
        self._art_name = name
        self._drawn = key
        self.info = info
        self.update(text)
        self.post_message(self.Drawn(self))

    def _draw(self):
        from ... import art

        if not self._art_name:
            return False
        size = self.content_size
        if not size.width or not size.height:
            return True
        key = (self._art_name, size.width, size.height)
        if key == self._drawn:
            return True
        chosen = getattr(self, "_art", None)
        if chosen is None:
            arts = art.library()
            chosen = arts.get(self._art_name) or arts.get("placeholder.txt")
        if chosen is not None and chosen.lines:
            self.update("\n".join(art.display_fit(chosen, size.width, size.height)))
            self._drawn = key
            self.info = art.fit_info(chosen, size.width, size.height)
            self.post_message(self.Drawn(self))
            return True
        self.update("")
        self._drawn = key
        self.info = None
        return False

    def on_mount(self):
        if self._art_name:
            self._draw()

    def on_resize(self, event):
        if self._art_name:
            self._draw()


class LogoBox(Static):
    def __init__(self, **kwargs):
        super().__init__("[#9db0e0]LOG O / IMG\n(drop art into\npaws/data/img/)[/]", **kwargs)
