from __future__ import annotations

import re
from pathlib import Path

from .dirs import user_art_dir
from .fit import trim
from .model import _COLEQ, _PALHDR, _PH, _STCOL, _TITLE, Art
from .palette import parse_entry, parse_palette_header, resolve_palette, palette_token


def parse_art(text: str, name: str, path: Path | None = None) -> Art:
    raw = text.splitlines()
    slots = []
    in_file = {}
    named = None
    title = ""
    index = 0

    for i, line in enumerate(raw):
        stripped = line.strip()
        m = _STCOL.match(raw[i])
        m2 = _COLEQ.match(raw[i])
        if m:
            slots = [int(n) for n in re.findall(r"\d+", m.group(1))]
            index = i + 1
            continue
        if m2:
            slots = [int(n) for n in re.findall(r"\d+", m2.group(1))]
            index = i + 1
            continue
        mt = _TITLE.match(raw[i])
        if mt:
            title = mt.group(1).strip()
            index = i + 1
            continue
        mp = _PALHDR.match(raw[i]) if stripped.lower().startswith("palette") else None
        if mp:
            in_file, named2 = parse_palette_header(mp.group(1))
            if named2 is not None:
                named = named2
            index = i + 1
            continue
        break

    body = [l for l in raw[index:] if l.strip()]
    palette = resolve_palette(slots, in_file or None, named, _load_sidecar(path))
    return Art(
        name=name,
        lines=trim(body),
        slots=slots,
        palette=palette,
        path=path,
        title=title,
        source="user" if path and user_art_dir() in path.parents else "bundled",
    )


def _load_sidecar(path):
    if not path:
        return None
    side = path.with_suffix(".palette")
    if not side.exists():
        return None
    out = {}
    for line in side.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        index, color = parse_entry(line)
        if index >= 0:
            out[index] = color if color is not None else None
    return out or None


def token_for(art: Art, number: int, fallback: str | None) -> str | None:
    if not art.slots:
        return fallback
    if 1 <= number <= len(art.slots):
        slot = art.slots[number - 1]
        return palette_token(art.palette.get(slot))
    return palette_token(art.palette.get(number))


def escape_markup(text):
    if not text or ("[" not in text and "]" not in text):
        return text
    return text.replace("[", "[[").replace("]", "]]")


def markup_lines(art: Art, fallback: str | None = None) -> list[str]:
    out = []
    current_color = None
    for line in art.lines:
        if not art.colored:
            out.append(escape_markup(line))
            continue
        segs = []
        position = 0
        for m in _PH.finditer(line):
            pre = line[position : m.start()]
            segs.append((pre, current_color))
            current_color = token_for(art, int(m.group(1)), fallback)
            position = m.end()
        segs.append((line[position:], current_color))
        built = []
        for seg, tok in segs:
            if not seg:
                continue
            if tok:
                built.append(f"[{tok}]{escape_markup(seg)}[/]")
            else:
                built.append(escape_markup(seg))
        out.append("".join(built))
    return out


def plain_lines(art: Art) -> list[str]:
    return [_PH.sub("", l) for l in art.lines]
