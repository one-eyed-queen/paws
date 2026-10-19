from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..util.backup import backup_file
from .io import raw_lines, write
from .seed import ensure_config
from .where import find_config


def _render_value(value: str) -> str:
    """how to write a value so yaml can read it back as the same string.

    the value used to be dropped in raw, so setting a key to "a: b" wrote "Key: a: b" and left a
    config that would not parse at all - one stray colon and SLSsteam's config is broken.

    yes/no/true/false and bare numbers stay unquoted on purpose: SLSsteam reads those as
    booleans and numbers, and quoting them would turn them into strings.
    """
    text = str(value)
    if text == "":
        return '""'
    needs_quotes = (
        ": " in text
        or text.rstrip().endswith(":")
        or " #" in text
        or text != text.strip()
        or text[0] in "-?:,[]{}#&*!|>'\"%@`"
    )
    if not needs_quotes:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        body = text[1:-1]
        if text[0] == '"':
            return body.replace('\\"', '"').replace("\\\\", "\\")
        return body
    return text


def _split_value(line: str, key: str) -> tuple[str, str] | None:
    """pull (value, comment) out of a "Key: value # comment" line, respecting quotes.

    the old regex was `(?P<v>.*?)(?P<c>\\s+#.*)?$` with a lazy value, so on a line that already
    held a quoted value it preferred to treat the tail as a comment: a key set to "a: b" and then
    to "hello" became 'hello: b"'. anything quoted has to be matched with a scan, not a regex.
    """
    m = re.match(rf"^\s*{re.escape(key)}:[ \t]*(.*)$", line)
    if not m:
        return None
    rest = m.group(1)
    stripped = rest.lstrip()
    if stripped[:1] in ('"', "'"):
        quote = stripped[0]
        i = 1
        while i < len(stripped):
            if stripped[i] == "\\" and quote == '"':
                i += 2
                continue
            if stripped[i] == quote:
                break
            i += 1
        if i < len(stripped):  # a closing quote, so the tail is a real comment
            return stripped[: i + 1], stripped[i + 1 :]
    # no quotes: a comment is a '#' that follows whitespace and is not inside a flow collection
    depth = 0
    for i, ch in enumerate(stripped):
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "#" and depth == 0 and i > 0 and stripped[i - 1] in " \t":
            return stripped[:i].rstrip(), stripped[i:]
    return stripped.rstrip(), ""


def set_scalar(key: str, value: str, backup: bool = True) -> bool:
    path = ensure_config()
    if backup:
        backup_file(path)
    lines = raw_lines(path)
    rendered = _render_value(value)
    for i, l in enumerate(lines):
        found = _split_value(l, key)
        if found is None:
            continue
        comment = found[1]
        lines[i] = f"{key}: {rendered}{comment if comment.startswith('#') else ''}"
        write(path, "\n".join(lines) + "\n")
        return True
    if not (lines and lines[-1].strip() == ""):
        lines.append("")
    lines.append(f"{key}: {rendered}")
    write(path, "\n".join(lines) + "\n")
    return True


def get_scalar(key: str) -> str | None:
    for l in raw_lines():
        found = _split_value(l, key)
        if found is not None:
            return _unquote(found[0])
    return None


def parsed(path: Path | None = None) -> dict:
    p = path or find_config()
    if p and p.exists():
        try:
            data = yaml.safe_load(p.read_text()) or {}
            if isinstance(data, dict):
                return data
        except yaml.YAMLError:
            pass
    return {}


def get_list(section: str) -> list[str]:
    d = parsed()
    v = d.get(section)
    if isinstance(v, list):
        return [str(x) for x in v]
    return []
