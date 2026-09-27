from __future__ import annotations

import re


def _indent(line):
    return len(line) - len(line.lstrip(" \t"))


def section_index(lines, section):
    for i, l in enumerate(lines):
        if l.startswith(f"{section}:"):
            return i
    return None


def block_end_line(lines, start):
    i = start + 1
    while i < len(lines):
        if lines[i].strip() and not lines[i].startswith((" ", "\t")):
            break
        i += 1
    return i


def child_end_line(lines, key_i, limit):
    n = _indent(lines[key_i])
    j = key_i + 1
    while j < limit and (not lines[j].strip() or _indent(lines[j]) > n):
        j += 1
    while j > key_i + 1 and not lines[j - 1].strip():
        j -= 1
    return j


_QUOTED = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'')


def _code_part(line):
    line = _QUOTED.sub('""', line)
    return re.split(r"(?:^|\s)#", line, maxsplit=1)[0]


def item_key(line):
    m = re.match(r"""^\s*(?:-\s*)?["']?(\w+)["']?\s*(?::|#|$|\s)""", line)
    return m.group(1) if m else None


def _matches_id(rendered, appid):
    return re.search(r"(?<!\d)" + re.escape(str(appid)) + r"(?!\d)", _code_part(rendered)) is not None
