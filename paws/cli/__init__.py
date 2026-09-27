from __future__ import annotations

import os
import sys

__all__ = ["main", "entrypoint", "build_parser"]

_MENU_FLAGS = {"-w", "--window", "--no-update", "menu"}


def __getattr__(name: str):
    if name == "COMMANDS":
        from .commands import COMMANDS

        return COMMANDS
    if name == "build_parser":
        from .parser import build_parser

        return build_parser
    raise AttributeError(name)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if all(a in _MENU_FLAGS for a in argv):
        if "--no-update" in argv:
            os.environ["PAWS_NO_UPDATE"] = "1"
        have_tty = sys.stdin.isatty() and sys.stdout.isatty()
        if "-w" in argv or "--window" in argv or (not have_tty and "menu" not in argv):
            from .window import open_window

            return open_window()
        from .commands import menu

        return menu.run(None)
    from .commands import COMMANDS
    from .parser import build_parser
    from .window import open_window

    args = build_parser().parse_args(argv)
    if args.no_update:
        os.environ["PAWS_NO_UPDATE"] = "1"
    have_tty = sys.stdin.isatty() and sys.stdout.isatty()
    if args.window or (args.command is None and not have_tty):
        return open_window()
    _remember_good_config()
    return COMMANDS[args.command or "menu"].run(args)


def _remember_good_config():
    from .. import repair

    try:
        repair.refresh_known_good()
    except Exception:
        pass


def entrypoint():
    sys.exit(main())
