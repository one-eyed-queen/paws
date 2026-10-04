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

from .widgets import backdrop, hires, scene

Z_BG = -1_500_000_000
MAX_SIDE = 1600
TICK = 0.3
REPLACE_EVERY = 4.0
RESEND_EVERY = 60.0


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


def transmit_png(image_id: int, png: bytes, cols: int, rows: int, *, x: int = 0, y: int = 0, z: int = Z_BG) -> str:
    payload = base64.b64encode(png).decode()
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)] or [""]
    parts = []
    for n, chunk in enumerate(chunks):
        more = 1 if n < len(chunks) - 1 else 0
        ctrl = f"a=T,f=100,i={image_id},p=1,c={cols},r={rows},z={z},C=1,q=2,m={more}" if n == 0 else f"m={more},q=2"
        parts.append(f"\x1b_G{ctrl};{chunk}\x1b\\")
    return f"\x1b7\x1b[{y + 1};{x + 1}H" + "".join(parts) + "\x1b8"


def png_bytes(image, level: int = 1) -> bytes:
    import io

    buf = io.BytesIO()
    image.save(buf, "PNG", compress_level=level)
    return buf.getvalue()


def place_sequence(image_id: int, cols: int, rows: int, *, x: int = 0, y: int = 0, z: int = Z_BG) -> str:
    return f"\x1b7\x1b[{y + 1};{x + 1}H\x1b_Ga=p,i={image_id},p=1,c={cols},r={rows},z={z},C=1,q=2\x1b\\\x1b8"


def delete_sequence(image_id: int) -> str:
    return f"\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\"


def hide_sequence(image_id: int) -> str:
    return f"\x1b_Ga=d,d=i,i={image_id},q=2\x1b\\"


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
        for scr in reversed(self.app.screen_stack):
            if not isinstance(scr, ModalScreen):
                return None if getattr(scr, "no_screen_picture", False) else scr
        return None

    async def _tick(self):
        if self.busy or self.paused:
            return
        scr = self._screen()
        if scr is None:
            self._hide()
            return
        size = self.app.size
        cols, rows = self._region(scr, size)
        now = time.monotonic()
        if self.bg_size == (cols, rows) and self.bg_id is not None:
            if not self.bg_shown:
                self._send(place_sequence(self.bg_id, cols, rows))
                self.bg_shown = True
                self.placed_at = now
                self.app.screen.refresh()
                return
            if now - self.sent_at > RESEND_EVERY:
                await self._apply(cols, rows)
            elif now - self.placed_at > REPLACE_EVERY:
                self.placed_at = now
                self._send(place_sequence(self.bg_id, cols, rows))
            return
        await self._apply(cols, rows)

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

    def _scaled_cell(self, cols):
        cw, ch = hires.CELL
        k = min(1.0, MAX_SIDE / max(1, cols * cw))
        return max(1, int(cw * k)), max(1, int(ch * k))

    async def _apply(self, cols, rows):
        self.busy = True
        try:
            cell = self._scaled_cell(cols)
            png = await asyncio.to_thread(lambda: png_bytes(scene.compose(cols, rows, cell)))
            if self._screen() is None or self.app.size.width != cols or self.app.size.height != rows:
                return
            old_bg = self.bg_id
            new_id = next(self._ids)
            self._send(transmit_png(new_id, png, cols, rows, z=Z_BG))
            self.bg_id, self.bg_size, self.bg_shown = new_id, (cols, rows), True
            now = time.monotonic()
            self.sent_at = self.placed_at = now
            if old_bg is not None:
                self._send(delete_sequence(old_bg))
            self.app.screen.refresh()
        finally:
            self.busy = False
