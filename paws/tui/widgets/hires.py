from __future__ import annotations

import logging
import os
import sys

from ... import settings

Image = None
CELL = (10, 20)
_GRAPHICS = False
_TGP = False

if sys.__stdout__ is not None and sys.__stdout__.isatty():
    try:
        logging.getLogger("textual_image").setLevel(logging.CRITICAL)
        import textual_image._terminal as _probe

        _probe._PROBE_TIMEOUT = 0.7
        from textual_image._terminal import get_cell_size
        from textual_image.renderable import Image as _Renderable
        from textual_image.renderable import SixelImage, TGPImage
        from textual_image.widget import Image as _Widget

        if _Renderable in (TGPImage, SixelImage):
            _GRAPHICS = True
            _TGP = _Renderable is TGPImage
            Image = _Widget
            size = get_cell_size()
            CELL = (max(1, int(size.width)), max(1, int(size.height)))
    except Exception:
        Image = None
        _GRAPHICS = False


def measure() -> tuple[float, float] | None:
    try:
        import fcntl
        import struct
        import termios

        rows, cols, xpix, ypix = struct.unpack(
            "HHHH", fcntl.ioctl(sys.__stdout__.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
        )
    except Exception:
        return None
    if not (rows and cols and xpix and ypix):
        return None
    return xpix / cols, ypix / rows


def cell() -> tuple[float, float]:
    global CELL
    live = measure()
    if live is None:
        return float(CELL[0]), float(CELL[1])
    CELL = (max(1, round(live[0])), max(1, round(live[1])))
    _sync_probe(CELL)
    return live


def _sync_probe(size: tuple[int, int]) -> None:
    # textual_image probes the terminal's cell size once at startup and caches it forever
    # (textual_image._terminal.probe_terminal). if the real cell size changes later - a kitty
    # zoom, say - our own live measurement and its stale cache disagree on how many pixels a
    # cell holds, and images it sends get scaled against the wrong number. keep its cache
    # pointed at whatever we just measured.
    try:
        import textual_image._terminal as t

        caps = getattr(t.probe_terminal, "_result", None)
        if caps is not None and tuple(caps.cell_size) != size:
            t.probe_terminal._result = caps._replace(cell_size=t.CellSize(*size))
    except Exception:
        pass


def available() -> bool:
    return _GRAPHICS and Image is not None and not settings.is_minimal()


def underlay_ok() -> bool:
    if not (_GRAPHICS and _TGP):
        return False
    env = os.environ
    return bool(
        env.get("KITTY_WINDOW_ID") or env.get("GHOSTTY_RESOURCES_DIR") or env.get("TERM", "").startswith("xterm-kitty")
    )


def _stable_render(self):
    key = (self._get_styled_size(), id(self._image))
    kept = getattr(self, "_kept", None)
    if self._renderable is not None and kept is not None and kept[0] == key and kept[1] is self._renderable:
        return self._renderable
    out = type(self).render(self)
    self._kept = (key, self._renderable)
    return out


def picture(pil, **kwargs):
    import types

    widget = Image(pil, **kwargs)
    widget.backdrop_off = True
    if hasattr(widget, "_get_styled_size") and hasattr(widget, "_renderable"):
        widget.render = types.MethodType(_stable_render, widget)
    return widget
