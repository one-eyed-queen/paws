from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LUACMD = re.compile(r"^(\w+)\s*\(", re.MULTILINE)


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
            command, args_str, comment = parse_call(text, m.start())
            command = command.lower()
            if command not in ("addappid", "addtoken", "setmanifestid", "addapptoken", "setdepotkey"):
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


def parse_call(text: str, start: int) -> tuple[str, str, str]:
    open_i = text.find("(", start)
    close_i = text.find(")", open_i)
    if close_i == -1:
        return text[start:].split("(")[0], "", ""
    args = text[open_i + 1 : close_i]
    rest = text[close_i + 1 : close_i + 300]
    comment = ""
    mm = re.search(r"--\s*([^\n]*)", rest)
    if mm:
        comment = mm.group(1).strip()
    command = text[start:open_i].strip()
    return command, args, comment


def split_args(s: str) -> list[str]:
    return s.split(",")
