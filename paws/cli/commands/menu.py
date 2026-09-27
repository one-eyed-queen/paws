from __future__ import annotations

import sys

NAME = "menu"


def add_parser(subparsers, common):
    subparsers.add_parser(NAME, help="open the full-screen TUI in this terminal (default when run in one)")


def run(args) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "paws: the menu needs a real terminal. run it in one, or use `paws --window`.",
            file=sys.stderr,
        )
        return 1
    from ... import update
    from ...tui import main as tui_main

    update.run(sys.argv[1:])

    return tui_main()
