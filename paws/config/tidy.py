from __future__ import annotations

import re

import yaml

from ..util.backup import backup_file
from .io import raw_lines, write
from .lines import block_end_line, section_index
from .where import find_config

# package ids are their own numbering, so a package row never borrows a label from an app with the same number
GAME_SECTIONS = ("AppIds", "AdditionalApps", "AdditionalPackageApps", "ManifestIds", "AppTokens", "DecryptionKeys")
SECTIONS = (*GAME_SECTIONS, "AdditionalPackages")
ROW = re.compile(r"""^\s+(?:-\s*)?["']?(\d+)["']?\s*(?::.*)?$""")
JUNK = re.compile(r"^\d*(?::\S*)?$")  # older paws wrote the id or the whole id:value row as the "name"


def split_comment(line: str) -> tuple[str, str]:
    quote = None
    for i, char in enumerate(line):
        if quote:
            quote = None if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip(), line[i + 1 :].strip()
    return line.rstrip(), ""


def _rows(lines, section):
    """(start, end, rows) for a section of plain one-line rows. a section with anything else in it (a hand written
    note, a nested block) returns None: that's somebody's own layout and not ours to shuffle"""
    index = section_index(lines, section)
    if index is None:
        return None
    start, end = index + 1, block_end_line(lines, index)
    rows = []
    for line in lines[start:end]:
        if not line.strip():
            continue
        code, label = split_comment(line)
        match = ROW.match(code)
        if not match:
            return None
        rows.append((match.group(1), code, "" if JUNK.fullmatch(label) else label))
    return start, end, rows


def unnamed_ids(path=None) -> list[str]:
    lines = raw_lines(path or find_config())
    found = {}
    for section in GAME_SECTIONS:
        block = _rows(lines, section)
        for appid, _code, label in block[2] if block else ():
            found[appid] = found.get(appid) or label
    return [appid for appid, label in found.items() if not label]


def _same_values(old: str, new: str) -> bool:
    def values(text):
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise yaml.YAMLError("not a mapping")
        for section in SECTIONS:
            if isinstance(data.get(section), list):
                data[section] = sorted(str(x) for x in data[section])
        return data

    try:
        return values(old) == values(new)
    except yaml.YAMLError:
        return False


def tidy(names: dict[str, str] | None = None, backup: bool = True) -> bool:
    """every game row gets its real name and each section reads alphabetically, so a game's rows are easy to find.
    only labels and order ever change. the write is refused unless the parsed config comes out the same, because
    a changed AdditionalApps list can make steam uninstall a game"""
    path = find_config()
    lines = raw_lines(path) if path else []
    if not lines:
        return False
    labels = dict(names or {})
    for section in GAME_SECTIONS:
        block = _rows(lines, section)
        for appid, _code, label in block[2] if block else ():
            if label:
                labels.setdefault(appid, label)
    out = list(lines)
    for section in SECTIONS:  # section_index on `out` stays right because a block keeps its line count
        block = _rows(out, section)
        if not block:
            continue
        start, end, rows = block
        named = []
        for appid, code, label in rows:
            label = label or ("" if section == "AdditionalPackages" else labels.get(appid, ""))
            named.append((not label, label.casefold(), int(appid), f"{code} # {label}" if label else code))
        named.sort(key=lambda row: row[:3])
        blanks = end - start - len(named)
        out[start:end] = [row[3] for row in named] + [""] * blanks
    old, new = "\n".join(lines) + "\n", "\n".join(out) + "\n"
    if old == new or not _same_values(old, new):
        return False
    if backup:
        backup_file(path)
    write(path, new)
    return True
