from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LUACMD = re.compile(r"(?m)(?:^|[^\w.])([A-Za-z_]\w*)\s*\(")
KNOWN_COMMANDS = (
    "addappid",
    "addtoken",
    "setmanifestid",
    "addapptoken",
    "setdepotkey",
    "adddlc",
    "adddlcname",
)


@dataclass
class LuaManifest:
    file: Path
    app_ids: list[tuple[int, str]] = field(default_factory=list)
    app_tokens: list[tuple[int, int, str]] = field(default_factory=list)
    manifest_ids: list[tuple[int, int, str]] = field(default_factory=list)
    decryption_keys: list[tuple[int, str, str]] = field(default_factory=list)
    dlc_names: dict[int, str] = field(default_factory=dict)

    def parse(self):
        text = self.file.read_text(errors="replace")
        for m in LUACMD.finditer(text):
            command, args_str, comment = parse_call(text, m.start(1))
            command = command.lower()
            if command not in KNOWN_COMMANDS:
                continue
            args = [a.strip().strip('"').strip("'") for a in split_args(args_str)]
            if command == "setdepotkey":
                if len(args) >= 2 and re.fullmatch(r"[0-9a-fA-F]{32,}", args[-1]):
                    try:
                        self.decryption_keys.append((int(args[0]), args[-1], comment))
                    except ValueError:
                        pass
            elif command in ("addappid", "addapptoken"):
                if not args:
                    continue
                try:
                    app_id = int(args[0])
                except ValueError:
                    continue
                key = args[-1] if len(args) >= 2 and re.fullmatch(r"[0-9a-fA-F]{32,}", args[-1]) else None
                self.app_ids.append((app_id, comment))
                if key:
                    self.decryption_keys.append((app_id, key, comment))
            elif command == "addtoken":
                if len(args) >= 2:
                    try:
                        self.app_tokens.append((int(args[0]), int(args[1]), comment))
                    except ValueError:
                        pass
            elif command == "setmanifestid":
                if len(args) >= 2:
                    try:
                        self.manifest_ids.append((int(args[0]), int(args[1]), comment))
                    except ValueError:
                        pass
            elif command in ("adddlc", "adddlcname"):
                # addDLC(<parent appid>, <dlc appid>, "<name>") - this is what puts a real name
                # on a dlc entry instead of leaving DlcData full of bare ids
                ids = [a for a in args if re.fullmatch(r"\d+", a)]
                if len(ids) >= 2:
                    name = next((a for a in args if not re.fullmatch(r"\d+", a)), "")
                    self.dlc_names.setdefault(int(ids[-1]), name or comment)


def _matching_paren(text: str, open_i: int) -> int:
    """the ')' that closes the '(' at open_i, ignoring any inside a quoted string.

    a plain find(")") cut the arguments short on any name containing brackets - "Strange Companion
    (Chapters)" lost its last two characters and the rest of the line with it.
    """
    depth = 0
    quote = ""
    i = open_i
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and i + 1 < len(text):
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_call(text: str, start: int) -> tuple[str, str, str]:
    open_i = text.find("(", start)
    if open_i == -1:
        return text[start:].split("(")[0].strip(), "", ""
    close_i = _matching_paren(text, open_i)
    if close_i == -1:
        return text[start:].split("(")[0].strip(), "", ""
    args = text[open_i + 1 : close_i]
    rest = text[close_i + 1 : close_i + 300]
    comment = ""
    mm = re.search(r"--\s*([^\n]*)", rest)
    if mm:
        comment = mm.group(1).strip()
    command = text[start:open_i].strip()
    return command, args, comment


def split_args(s: str) -> list[str]:
    """split on commas that are not inside a quoted string.

    this was s.split(","), which cut every name containing a comma in half: a DLC called
    "Soundtrack, Deluxe Edition" arrived as "Soundtrack". real store names have commas and colons
    and brackets in them all the time, so the split has to know about quoting.
    """
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(s):
        ch = s[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p for p in parts if p.strip()] if not any(parts) else parts
