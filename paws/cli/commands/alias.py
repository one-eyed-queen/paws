from __future__ import annotations

from ...shellalias import SHELLS, install_path, shells_in_use, snippet
from ...windows import IS_WINDOWS

NAME = "alias"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="put `paws` on your PATH (--install) or print a shell function")
    p.add_argument(
        "shell",
        nargs="?",
        choices=list(SHELLS),
        help="fish, zsh or bash; powershell on windows (default: bash to print, every shell you use to install)",
    )
    p.add_argument(
        "--install",
        action="store_true",
        help="add ~/.local/bin to that shell's PATH (fish: its own conf.d file; windows: paws' Scripts folder)",
    )


def run(args) -> int:
    if not args.install:
        print(snippet(args.shell or ("powershell" if IS_WINDOWS else "bash")))
        return 0
    shells = [args.shell] if args.shell else shells_in_use()
    if not shells:
        print("couldn't tell which shell you use. run `paws alias --install fish` (or zsh / bash)")
        return 1
    for sh in shells:
        r = install_path(sh)
        print(f"{sh}: {r.note} ({r.file})")
    print("open a new terminal for it to take effect")
    return 0
