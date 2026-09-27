from __future__ import annotations

from ... import appentry

NAME = "desktop"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="install (or remove) the paws icon + app-menu entry")
    p.add_argument("--shortcut", action="store_true", help="also put a paws icon on your desktop")
    p.add_argument(
        "--remove", action="store_true", help="take the icon, launcher entry and desktop shortcut away again"
    )


def run(args) -> int:
    results = []
    if args.remove:
        results = [appentry.uninstall(), appentry.remove_shortcut()]
    else:
        results = [appentry.install()]
        if args.shortcut:
            results.append(appentry.add_shortcut())
    for result in results:
        print(result.note)
        for f in result.files:
            print(f"  {f}")
    return 0 if all(r.ok for r in results) else 1
