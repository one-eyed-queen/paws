from __future__ import annotations

import base64
import fcntl
import io
import itertools
import os
import shutil
import struct
import sys
import termios
import threading
from contextlib import contextmanager
from pathlib import Path

from .. import __version__, settings
from ..paths import DATA_DIR
from .repo import short_name

BACKGROUND = DATA_DIR / "img" / "paws-bg.png"
IMAGE_ID = 917_001
Z_UNDER_TEXT = -1_500_000_000
BOX_COLS, BOX_ROWS = 62, 12
BLUR = 18
CANVAS = 1100
TINT = (10, 16, 32)
TINT_AMOUNT = 0.58
CYAN, LIGHT, DIM, GREEN, YELLOW, RED = "0;208;255", "235;240;255", "170;184;224", "95;240;160", "255;215;95", "255;122;138"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _fg(rgb: str, text: str, bold: bool = False) -> str:
    return f"\x1b[{'1;' if bold else ''}38;2;{rgb}m{text}\x1b[0m"


def _graphics_ok() -> bool:
    env = os.environ
    if settings.is_minimal() or env.get("TMUX") or env.get("STY") or env.get("SSH_TTY"):
        return False
    return bool(env.get("KITTY_WINDOW_ID") or env.get("GHOSTTY_RESOURCES_DIR") or env.get("TERM", "").startswith("xterm-kitty"))


def _cell_pixels() -> tuple[int, int]:
    try:
        rows, cols, xpix, ypix = struct.unpack("HHHH", fcntl.ioctl(sys.__stdout__.fileno(), termios.TIOCGWINSZ, b"\0" * 8))
        if rows and cols and xpix and ypix:
            return xpix // cols, ypix // rows
    except OSError:
        pass
    return 10, 20


def compose(cols: int, rows: int, box: tuple[int, int, int, int], cell: tuple[int, int]):
    """the picture across the whole window, with a pane of frosted glass cut into it behind the text"""
    from PIL import Image, ImageDraw, ImageFilter

    # the terminal scales it to the window anyway, so a smaller canvas costs nothing you can see and is much quicker
    cw, ch = cell
    fit = min(1.0, CANVAS / max(cols * cw, 1))
    cw, ch = max(1, round(cw * fit)), max(1, round(ch * fit))
    w, h = cols * cw, rows * ch
    src = Image.open(BACKGROUND).convert("RGB")
    k = max(w / src.width, h / src.height)
    big = src.resize((round(src.width * k) + 1, round(src.height * k) + 1), Image.BILINEAR)
    left, top = (big.width - w) // 2, (big.height - h) // 2
    picture = big.crop((left, top, left + w, top + h))
    x, y, bw, bh = box[0] * cw, box[1] * ch, box[2] * cw, box[3] * ch
    pane = picture.crop((x, y, x + bw, y + bh)).filter(ImageFilter.GaussianBlur(BLUR))
    pane = Image.blend(pane, Image.new("RGB", pane.size, TINT), TINT_AMOUNT)
    mask = Image.new("L", pane.size, 0)
    radius = min(cw, ch)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), radius, fill=255)
    picture.paste(pane, (x, y), mask)
    ImageDraw.Draw(picture).rounded_rectangle((x, y, x + bw - 1, y + bh - 1), radius, outline=(150, 175, 235), width=1)
    if settings.get_setting("colorblind") != "off":
        from ..tui import colorblind

        picture = colorblind.image(picture)
    return picture


class GlassSplash:
    """the update check, full screen and centred, on the alternate screen so nothing's left behind for the menu.
    same calls as the plain splash. terminals without kitty graphics get the same box on their own background"""

    def __init__(self):
        size = shutil.get_terminal_size((80, 24))
        self.cols, self.rows = size.columns, size.lines
        self.width = min(BOX_COLS, self.cols - 2)
        self.height = min(BOX_ROWS, self.rows)
        self.x = (self.cols - self.width) // 2
        self.y = (self.rows - self.height) // 2
        self.graphics = _graphics_ok()
        self.lines: list[str] = []
        self.status = ""
        self.lock = threading.Lock()
        self.open = False

    def _write(self, text: str) -> None:
        sys.__stdout__.write(text)
        sys.__stdout__.flush()

    def header(self):
        self.open = True
        self._write("\x1b[?1049h\x1b[?25l\x1b[2J")
        self._draw()  # the words first, the picture lands behind them a moment later
        if self.graphics:
            threading.Thread(target=self._picture_behind, daemon=True).start()

    def _picture_behind(self):
        try:
            self._send_picture()
        except Exception:  # a missing picture is no reason to hold up the menu
            self.graphics = False

    def _picture_bytes(self) -> bytes:
        """kept on disk per window size, so every start after the first has it instantly"""
        cell = _cell_pixels()
        mode = settings.get_setting("colorblind")
        key = f"{self.cols}x{self.rows}-{cell[0]}x{cell[1]}-{mode}-{BACKGROUND.stat().st_mtime_ns}"
        path = Path.home() / ".cache" / "paws" / f"splash-{key}.png"
        try:
            return path.read_bytes()
        except OSError:
            pass
        buffer = io.BytesIO()
        compose(self.cols, self.rows, (self.x, self.y, self.width, self.height), cell).save(buffer, "PNG", compress_level=1)
        data = buffer.getvalue()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob("splash-*.png"):
                old.unlink(missing_ok=True)
            path.write_bytes(data)
        except OSError:
            pass
        return data

    def _send_picture(self):
        payload = base64.b64encode(self._picture_bytes()).decode()
        chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)]
        out = ["\x1b[H"]
        for n, chunk in enumerate(chunks):
            more = int(n < len(chunks) - 1)
            ctrl = f"a=T,f=100,i={IMAGE_ID},c={self.cols},r={self.rows},z={Z_UNDER_TEXT},C=1,q=2,m={more}" if n == 0 else f"m={more},q=2"
            out.append(f"\x1b_G{ctrl};{chunk}\x1b\\")
        with self.lock:
            if self.open:
                self._write("\x1b7" + "".join(out) + "\x1b8")

    def _center(self, row: int, plain_length: int, text: str) -> str:
        column = self.x + max(0, (self.width - plain_length) // 2)
        return f"\x1b[{self.y + row + 1};{column + 1}H{text}"

    def _draw(self):
        with self.lock:
            if not self.open:
                return
            title = f"P A W S   v{__version__}"
            out = ["\x1b[2J" if not self.graphics else ""]
            for row in range(self.height):  # clear only inside the box, so the status can shrink without leftovers
                out.append(f"\x1b[{self.y + row + 1};{self.x + 1}H\x1b[0m" + " " * self.width)
            if not self.graphics:
                bar = "─" * (self.width - 2)
                out.append(f"\x1b[{self.y + 1};{self.x + 1}H" + _fg(DIM, f"╭{bar}╮"))
                for row in range(1, self.height - 1):
                    out.append(f"\x1b[{self.y + row + 1};{self.x + 1}H" + _fg(DIM, "│"))
                    out.append(f"\x1b[{self.y + row + 1};{self.x + self.width}H" + _fg(DIM, "│"))
                out.append(f"\x1b[{self.y + self.height};{self.x + 1}H" + _fg(DIM, f"╰{bar}╯"))
            out.append(self._center(2, len(title), _fg(CYAN, title, bold=True)))
            subtitle = "SLSsteam manager"
            out.append(self._center(3, len(subtitle), _fg(DIM, subtitle)))
            row = 5
            for plain, colored in self.lines[-4:]:
                out.append(self._center(row, len(plain), colored))
                row += 1
            if self.status:
                out.append(self._center(row, len(self.status), _fg(LIGHT, self.status)))
            self._write("".join(out))

    def _add(self, plain: str, colored: str):
        self.lines.append((plain[: self.width - 4], colored))
        self._draw()

    @contextmanager
    def working(self, label: str, detail: str):
        stop = threading.Event()

        def spin():
            for frame in itertools.cycle(SPINNER):
                self.status = f"{frame}  {detail}"
                self._draw()
                if stop.wait(0.1):
                    return

        thread = threading.Thread(target=spin, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()
            self.status = ""
            self._draw()

    def row(self, label: str, value: str, color: str):
        plain = f"{label}   {value}"
        self._add(plain, _fg(DIM, label) + "   " + _fg(color, value, bold=True))

    def note(self, text: str, color: str = DIM):
        self._add(text, _fg(color, text[: self.width - 4]))

    def show(self, status):
        from . import git

        kind, build = status.state, git.short(status.local)
        self.lines = []
        self.row(short_name(), "offline" if kind == "offline" else "online", DIM if kind == "offline" else GREEN)
        if kind == "current":
            self.row(build, "up to date", GREEN)
        elif kind == "updated":
            self.row(f"{build} → {git.short(status.remote)}", "updated", CYAN)
            for line in status.subjects[:2]:
                self.note("+ " + line)
        elif kind == "behind":
            self.row(f"{build} → {git.short(status.remote)}", "update available", YELLOW)
        elif kind == "blocked":
            self.row(build, "held", YELLOW)
            self.note(status.message, YELLOW)
        elif kind == "offline":
            self.note("skipping the update check")
        elif kind == "unmanaged":
            self.note("this copy updates through your package manager")
        elif kind == "error":
            self.row(build, "error", RED)
            self.note(status.message, RED)

    def close(self):
        if not self.open:
            return
        with self.lock:
            self.open = False
            self._write(f"\x1b_Ga=d,d=I,i={IMAGE_ID},q=2\x1b\\\x1b[?25h\x1b[?1049l")

    def hand_over(self) -> None:
        """stay on screen, and let the app take this alternate screen over: it paints straight on top, so there's no
        blank terminal while it starts. the app removes the picture with remove_picture once its first screen is up"""
        with self.lock:
            self.open = False


def remove_picture() -> str:
    return f"\x1b_Ga=d,d=I,i={IMAGE_ID},q=2\x1b\\"
