from __future__ import annotations

import asyncio
import base64
import itertools
import os
import time
import zlib
from random import randint

from textual.screen import ModalScreen

from .. import settings
from . import colorblind

from .widgets import backdrop, hires, scene

Z_BG = -1_500_000_000
MAX_SIDE = 1600
TICK = 0.05
REPLACE_EVERY = 4.0
PAINT_WAIT = 0.3  # a cached picture is ready instantly: give the new screen time to paint first
SETTLE_AFTER = (0.3, 0.8, 2.0)  # place it again soon after sending, so a placement lost in a screen change comes back
RESEND_EVERY = 60.0
WAIT = object()


def wanted() -> bool:
    if settings.is_minimal():
        return False
    forced = os.environ.get("PAWS_UNDERLAY")
    if forced in ("0", "1"):
        return forced == "1" and hires.available()
    if not hires.underlay_ok():
        return False
    env = os.environ
    if env.get("TMUX") or env.get("STY") or env.get("SSH_CONNECTION") or env.get("SSH_TTY"):
        return False
    return True


def transmit_sequence(
    image_id: int,
    data: bytes,
    size: tuple[int, int],
    cols: int,
    rows: int,
    *,
    x: int = 0,
    y: int = 0,
    z: int = Z_BG,
    alpha: bool = False,
) -> str:
    payload = base64.b64encode(zlib.compress(data, 1)).decode()
    w, h = size
    pixel_format = 32 if alpha else 24
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)] or [""]
    parts = []
    for n, chunk in enumerate(chunks):
        more = 1 if n < len(chunks) - 1 else 0
        if n == 0:
            ctrl = f"a=T,f={pixel_format},s={w},v={h},o=z,i={image_id},p=1,c={cols},r={rows},z={z},C=1,q=2,m={more}"
        else:
            ctrl = f"m={more},q=2"
        parts.append(f"\x1b_G{ctrl};{chunk}\x1b\\")
    return f"\x1b7\x1b[{y + 1};{x + 1}H" + "".join(parts) + "\x1b8"


def transmit_png(
    image_id: int, png: bytes, cols: int, rows: int, *, x: int = 0, y: int = 0, z: int = Z_BG, place: bool = True
) -> str:
    payload = base64.b64encode(png).decode()
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)] or [""]
    parts = []
    for n, chunk in enumerate(chunks):
        more = 1 if n < len(chunks) - 1 else 0
        if n > 0:
            ctrl = f"m={more},q=2"
        elif place:
            ctrl = f"a=T,f=100,i={image_id},p=1,c={cols},r={rows},z={z},C=1,q=2,m={more}"
        else:  # kept by the terminal, ready to show the moment a screen wants it
            ctrl = f"a=t,f=100,i={image_id},q=2,m={more}"
        parts.append(f"\x1b_G{ctrl};{chunk}\x1b\\")
    return f"\x1b7\x1b[{y + 1};{x + 1}H" + "".join(parts) + "\x1b8"


def png_bytes(image, level: int = 1) -> bytes:
    import io

    buf = io.BytesIO()
    image.save(buf, "PNG", compress_level=level)
    return buf.getvalue()


def place_sequence(image_id: int, cols: int, rows: int, *, x: int = 0, y: int = 0, z: int = Z_BG) -> str:
    return f"\x1b7\x1b[{y + 1};{x + 1}H\x1b_Ga=p,i={image_id},p=1,c={cols},r={rows},z={z},C=1,q=2\x1b\\\x1b8"


def hide_sequence(image_id: int) -> str:
    """lower case d=i: off the screen, but the terminal keeps the picture"""
    return f"\x1b_Ga=d,d=i,i={image_id},q=2\x1b\\"


def delete_sequence(image_id: int) -> str:
    return f"\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\"


_pictures: dict[tuple, bytes] = {}  # building one is the slow part, and every screen change needs one


def _picture(cols, rows, cell, box=None) -> bytes:
    """box: a pane of frosted glass behind a popup or the home menu, over the sharp picture, like the loading screen.
    no box: the soft blurred wallpaper the other pages sit on"""
    key = (cols, rows, cell, box, colorblind.mode())
    if key not in _pictures:
        if box is None:
            picture = scene.compose(cols, rows, cell)
        else:
            from ..update.glass import compose as glass

            picture = glass(cols, rows, box, cell, colours=False)
        png = png_bytes(colorblind.image(picture))
        while len(_pictures) >= 6:
            _pictures.pop(next(iter(_pictures)))
        _pictures[key] = png
    return _pictures[key]


class Underlay:
    def __init__(self, app):
        self.app = app
        self._ids = itertools.count(randint(1, 2**24))
        self.timer = None
        self.busy = False
        self.paused = False
        self.bg_id: int | None = None
        self.bg_size: tuple[int, int] | None = None
        self.bg_shown = False
        self.sent_at = 0.0
        self.placed_at = 0.0
        self._seen, self._seen_at = None, 0.0
        self._settle: tuple[float, ...] = ()

    def start(self):
        if wanted():
            backdrop.UNDERLAY = True
            self.timer = self.app.set_interval(TICK, self._tick)

    def pause(self):
        self.paused = True
        if self.bg_id is not None:
            self._send(delete_sequence(self.bg_id))
        self.bg_id, self.bg_size, self.bg_shown = None, None, False

    def resume(self):
        self.paused = False

    def stop(self):
        backdrop.UNDERLAY = False
        if self.timer is not None:
            self.timer.stop()
        if self.bg_id is not None:
            self._send(delete_sequence(self.bg_id))
        self.bg_id, self.bg_size, self.bg_shown = None, None, False

    def _send(self, escape_sequence):
        try:
            self.app._driver.write(escape_sequence)
        except Exception:
            pass

    def _screen(self):
        top = self.app.screen_stack[-1] if self.app.screen_stack else None
        if isinstance(top, ModalScreen) and backdrop.glass_popup(top):
            return top  # a popup gets its own picture: sharp, with a glass pane behind the box
        for scr in reversed(self.app.screen_stack):
            if not isinstance(scr, ModalScreen):
                return None if getattr(scr, "no_screen_picture", False) else scr
        return None

    @staticmethod
    def _glass_box(scr):
        """where the frosted pane goes: the popup's box, or what the screen names with glass_box(). WAIT until laid out"""
        if isinstance(scr, ModalScreen):
            boxes = [child.region for child in scr.children if child.region.width and child.region.height]
            region = max(boxes, key=lambda r: r.width * r.height) if boxes else None  # the popup's own box
        else:
            name = getattr(scr, "glass_box", None)
            region = name() if callable(name) else None
            if region is None:
                return None
        if region is None or not region.width or not region.height:
            return WAIT
        return (region.x, region.y, region.width, region.height)

    async def _tick(self):
        if self.busy or self.paused:
            return
        scr = self._screen()
        if scr is None:
            self._hide()
            await self._preload()
            return
        size = self.app.size
        cols, rows = self._region(scr, size)
        box = self._glass_box(scr)
        if box is WAIT:
            return
        key = (cols, rows, box)
        now = time.monotonic()
        if scr is not self._seen:
            self._seen, self._seen_at = scr, now
        if self.bg_id is None and now - self._seen_at < PAINT_WAIT:
            return
        if self.bg_size == key and self.bg_id is not None:
            if not self.bg_shown:
                self._send(place_sequence(self.bg_id, cols, rows))
                self.bg_shown = True
                self.placed_at = self.sent_at = now
                self._settle = SETTLE_AFTER
                self.app.screen.refresh()
                return
            if self._settle and now - self.sent_at > self._settle[0]:
                self._settle = self._settle[1:]
                self.placed_at = now
                self._send(place_sequence(self.bg_id, cols, rows))
            elif now - self.sent_at > RESEND_EVERY:
                await self._apply(cols, rows, box)
            elif now - self.placed_at > REPLACE_EVERY:
                self.placed_at = now
                self._send(place_sequence(self.bg_id, cols, rows))
            return
        await self._apply(cols, rows, box)

    def _region(self, scr, size):
        # a screen can shrink the background to its left-hand columns (e.g. to leave a plain
        # terminal area behind a real graphics widget elsewhere on the screen, which the
        # wallpaper's own kitty image would otherwise sit underneath/compete with) by defining
        # background_cols() -> int
        limit = getattr(scr, "background_cols", None)
        if callable(limit):
            try:
                limit = limit()
            except Exception:
                limit = None
        cols = limit if isinstance(limit, int) and 0 < limit < size.width else size.width
        return cols, size.height

    def _hide(self):
        if self.bg_id is not None and self.bg_shown:
            self._send(hide_sequence(self.bg_id))
            self.bg_shown = False

    async def _preload(self):
        """the home screen has no wallpaper, so this is when the next screen's gets ready: built, sent, not shown"""
        size = self.app.size
        region = (size.width, size.height, None)
        if not size.width or (self.bg_id is not None and self.bg_size == region):
            return
        self.busy = True
        try:
            png = await asyncio.to_thread(_picture, size.width, size.height, self._scaled_cell(size.width))
            old_bg, new_id = self.bg_id, next(self._ids)
            self._send(transmit_png(new_id, png, size.width, size.height, place=False))
            self.bg_id, self.bg_size, self.bg_shown = new_id, region, False
            self.sent_at = time.monotonic()
            if old_bg is not None:
                self._send(delete_sequence(old_bg))
        finally:
            self.busy = False

    def _scaled_cell(self, cols):
        cw, ch = hires.CELL
        k = min(1.0, MAX_SIDE / max(1, cols * cw))
        return max(1, int(cw * k)), max(1, int(ch * k))

    async def _apply(self, cols, rows, box=None):
        self.busy = True
        try:
            cell = self._scaled_cell(cols)
            png = await asyncio.to_thread(_picture, cols, rows, cell, box)
            # compared to what the screen wants now, not the window: a screen can ask for fewer columns (add game
            # does), and comparing to the window threw that picture away, leaving no background at all
            scr = self._screen()
            if scr is None or self._region(scr, self.app.size) != (cols, rows) or self._glass_box(scr) != box:
                return
            old_bg = self.bg_id
            new_id = next(self._ids)
            self._send(transmit_png(new_id, png, cols, rows, z=Z_BG))
            self.bg_id, self.bg_size, self.bg_shown = new_id, (cols, rows, box), True
            now = time.monotonic()
            self.sent_at = self.placed_at = now
            self._settle = SETTLE_AFTER
            if old_bg is not None:
                self._send(delete_sequence(old_bg))
            self.app.screen.refresh()
        finally:
            self.busy = False
