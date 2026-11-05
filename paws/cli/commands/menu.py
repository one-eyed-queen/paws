from __future__ import annotations

import os
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
    if os.name == "nt":
        from ... import update
        from ...tui import main as tui_main

        update.run(sys.argv[1:])
        return tui_main()
    from ...update.glass import GlassSplash

    splash = GlassSplash()  # up before anything slow, down once the menu can draw: no blank terminal in between
    splash.header()
    try:
        from ... import update

        update.run(sys.argv[1:], splash)
        with splash.working("", "loading"):
            from ...tui import main as tui_main
    except BaseException:
        splash.close()
        raise
    splash.status = "loading"
    splash.hand_over()
    return tui_main()
