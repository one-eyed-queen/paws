from __future__ import annotations

import sys

from ... import editor
from ...config import ensure_config

NAME = "edit"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="open config.yaml in nvim (or nano) and check it after", parents=[common])
    p.add_argument("section", nargs="?", help="open at this key, like AdditionalApps")


def run(args) -> int:
    path = ensure_config()
    line = editor.section_line(path, args.section) if args.section else None
    result = editor.edit(path, line)
    if not result.ran:
        print(result.error, file=sys.stderr)
        return 1
    if result.problem:
        print(f"config.yaml is broken yaml now: {result.problem}")
        if sys.stdin.isatty() and input("put the version from before this edit back? [y/N] ").strip().lower() == "y":
            print("your old config is back" if editor.put_back(path, result.backup) else "couldn't put it back")
        return 1
    print(f"saved in {result.editor}, valid yaml" if result.changed else "nothing changed")
    return 0
