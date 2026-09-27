from __future__ import annotations

from functools import lru_cache

from rich.cells import cell_len

_BLANK = set(" \t ⠀　​‌‍‎‏⁠﻿")


def is_blank(ch: str) -> bool:
    return ch in _BLANK or ch.isspace()


def _is_braille(ch):
    return "⠀" <= ch <= "⣿"


_BLANKS = "".join(
    sorted(
        _BLANK
        | set("\t\n\v\f\r\x1c\x1d\x1e\x1f\x85\xa0\u1680\u2028\u2029\u202f\u205f")
        | {chr(c) for c in range(0x2000, 0x200B)}
    )
)


def trim(lines: list[str]) -> list[str]:
    rows = list(lines)
    while rows and not rows[0].strip(_BLANKS):
        rows.pop(0)
    while rows and not rows[-1].strip(_BLANKS):
        rows.pop()
    if not rows:
        return []
    inked = [line for line in rows if line.strip(_BLANKS)]
    left = min(len(line) - len(line.lstrip(_BLANKS)) for line in inked)
    right = max(len(line.rstrip(_BLANKS)) for line in inked)
    return [line[left:right] for line in rows]


def size(lines: list[str]) -> tuple[int, int]:
    return max((cell_len(l) for l in lines), default=0), len(lines)


def _mostly_braille(lines):
    ink = [c for l in lines for c in l if not is_blank(c) or _is_braille(c)]
    return bool(ink) and sum(_is_braille(c) for c in ink) * 2 >= len(ink)


_DOTS = ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3))


def _to_bitmap(lines, w):
    from PIL import Image

    image = Image.new("L", (w * 2, len(lines) * 4), 0)
    px = image.load()
    for row, line in enumerate(lines):
        for col, ch in enumerate(line[:w]):
            mask = ord(ch) - 0x2800 if _is_braille(ch) else (0 if is_blank(ch) else 0xFF)
            for bit, (dx, dy) in enumerate(_DOTS):
                if mask >> bit & 1:
                    px[col * 2 + dx, row * 4 + dy] = 255
    return image


def _from_bitmap(image):
    px = image.load()
    cols, rows = image.width // 2, image.height // 4
    out = []
    for row in range(rows):
        chars = []
        for col in range(cols):
            mask = 0
            for bit, (dx, dy) in enumerate(_DOTS):
                if px[col * 2 + dx, row * 4 + dy]:
                    mask |= 1 << bit
            chars.append(chr(0x2800 + mask))
        out.append("".join(chars))
    return out


def _shrink_braille(lines, cols, rows):
    from PIL import Image

    w = max(len(l) for l in lines)
    h = len(lines)
    s = min(cols / w, rows / h, 1.0)
    dw = max(2, min(cols * 2, round(w * 2 * s)))
    dh = max(4, min(rows * 4, round(h * 4 * s)))
    image = _to_bitmap(lines, w).resize((dw, dh), Image.BOX).convert("1")
    padded = Image.new("1", (-(-dw // 2) * 2, -(-dh // 4) * 4), 0)
    padded.paste(image, (0, 0))
    return _from_bitmap(padded)


def _shrink_text(lines, cols, rows):
    w, h = size(lines)
    s = min(cols / w, rows / h, 1.0)
    nw = max(1, min(cols, int(w * s)))
    nh = max(1, min(rows, int(h * s)))
    picked = [lines[min(h - 1, int(i * h / nh))] for i in range(nh)]
    out = []
    for line in picked:
        n = len(line)
        if cell_len(line) > nw:
            line = "".join(line[min(n - 1, int(i * n / nw))] for i in range(nw)) if n else line
        while line and cell_len(line) > nw:
            line = line[:-1]
        out.append(line)
    return out


@lru_cache(maxsize=96)
def _fit_cached(lines, cols, rows):
    rows_ = trim(list(lines))
    if not rows_:
        return ()
    w, h = size(rows_)
    cols = w if not cols or cols <= 0 else cols
    rows = h if not rows or rows <= 0 else rows
    if w <= cols and h <= rows:
        return tuple(rows_)
    if _mostly_braille(rows_):
        return tuple(_shrink_braille(rows_, cols, rows))
    return tuple(_shrink_text(rows_, cols, rows))


def fit(lines: list[str], cols: int | None, rows: int | None) -> list[str]:
    return list(_fit_cached(tuple(lines), cols, rows))
