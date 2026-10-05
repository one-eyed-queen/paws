from __future__ import annotations

from ..util.backup import backup_file
from .io import raw_lines, write
from .lines import (
    block_end_line,
    child_end_line,
    _code_part,
    _indent,
    item_key,
    _matches_id,
    section_index,
)
from .schema import ConfigError, section_schema
from .seed import ensure_config


def render_item(section: str, fields: dict | None = None, **kwargs) -> str:
    schema = section_schema(section)
    item_tpl = schema.get("item")
    if not item_tpl:
        raise ConfigError(f"section {section} has no item template")
    merged = {**(fields or {}), **kwargs}
    return item_tpl.format(**merged)


def add_entry(section: str, rendered: str, backup: bool = True) -> tuple[bool, str | None]:
    path = ensure_config()
    bak = backup_file(path) if backup else None
    lines = raw_lines(path)
    index = section_index(lines, section)
    if index is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(f"{section}:")
        lines.append(rendered)
    else:
        needle = " ".join(rendered.split())
        key, ind = item_key(rendered), _indent(rendered)
        for l in lines[index + 1 : block_end_line(lines, index)]:
            if " ".join(l.split()) == needle:
                return False, bak
            if key is not None and _indent(l) == ind and item_key(l) == key and not l.lstrip().startswith("#"):
                return False, bak
        lines.insert(index + 1, rendered)
    write(path, "\n".join(lines) + "\n")
    return True, bak


def add_map_list_item(section: str, fields: dict, backup: bool = True) -> tuple[bool, str | None]:
    """one item under its key in a map-list section (DenuvoGames: steamid -> appids), making the key if needed"""
    schema = section_schema(section)
    key_line, item = schema["key"].format(**fields), schema["item"].format(**fields)
    path = ensure_config()
    bak = backup_file(path) if backup else None
    lines = raw_lines(path)
    index = section_index(lines, section)
    if index is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines += [f"{section}:", key_line, item]
    else:
        end = block_end_line(lines, index)
        key = item_key(key_line)
        at = next(
            (i for i in range(index + 1, end) if _indent(lines[i]) == _indent(key_line) and item_key(lines[i]) == key),
            None,
        )
        if at is None:
            lines[index + 1 : index + 1] = [key_line, item]
        else:
            child_end = child_end_line(lines, at, end)
            if any(_matches_id(l, str(fields["appid"])) for l in lines[at + 1 : child_end]):
                return False, bak
            lines.insert(child_end, item)
    write(path, "\n".join(lines) + "\n")
    return True, bak


def remove_rendered(section: str, rendered: str, backup: bool = True) -> tuple[bool, str | None]:
    path = ensure_config()
    bak = backup_file(path) if backup else None
    lines = raw_lines(path)
    index = section_index(lines, section)
    if index is None:
        return False, bak
    needle = " ".join(rendered.split())
    end = block_end_line(lines, index)
    kept = [l for l in lines[index + 1 : end] if " ".join(l.strip().split()) != needle]
    removed = len(kept) != end - index - 1
    if removed:
        write(path, "\n".join(lines[: index + 1] + kept + lines[end:]) + "\n")
    return removed, bak


def remove_entry(section: str, appid: str, backup: bool = True) -> tuple[bool, str | None]:
    path = ensure_config()
    bak = backup_file(path) if backup else None
    lines = raw_lines(path)
    index = section_index(lines, section)
    if index is None:
        return False, bak
    end = block_end_line(lines, index)
    out = []
    removed = False
    i = index + 1
    while i < end:
        l = lines[i]
        if l.strip() and _matches_id(l, str(appid)):
            removed = True
            if _code_part(l).rstrip().endswith(":") and l.startswith((" ", "\t")):
                i = child_end_line(lines, i, end)
                continue
            i += 1
            continue
        out.append(l)
        i += 1
    if removed:
        write(path, "\n".join(lines[: index + 1] + out + lines[end:]) + "\n")
    return removed, bak


def refs_for(appid: str) -> list[tuple[str, str]]:
    out = []
    for l in raw_lines():
        if _matches_id(l, str(appid)):
            out.append((l.strip().split(":")[0].strip() or l.strip(), l))
    return out
