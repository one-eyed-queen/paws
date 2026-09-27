from __future__ import annotations

import argparse

from .. import __version__

VERSION_TEXT = (
    f"paws {__version__}\n\nSource-available © 2026 ken (kaneki ken) / Anteiku - "
    "no resale, no rebrand, no AI training (see LICENSE)."
)


def build_parser() -> argparse.ArgumentParser:
    from .commands import COMMANDS

    p = argparse.ArgumentParser(prog="paws", description="menu-driven SLSsteam manager for Linux")
    p.add_argument("--version", action="version", version=VERSION_TEXT)
    p.add_argument("-w", "--window", action="store_true", help="open paws in a new terminal window instead of this one")
    p.add_argument("--no-update", action="store_true", help="don't look for a newer paws on github this time")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="json output, no menu")
    subparsers = p.add_subparsers(dest="command")
    for command in COMMANDS.values():
        command.add_parser(subparsers, common)
    return p
