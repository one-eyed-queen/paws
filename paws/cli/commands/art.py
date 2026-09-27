from __future__ import annotations

import json
import sys

from ... import art

NAME = "art"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="ASCII art gallery / home banner", parents=[common])
    p.add_argument("name", nargs="?", help="render a specific art, or 'random' to pick one at random")
    p.add_argument(
        "pool", nargs="?", choices=["sfw", "both", "nsfw"], help="pool for 'random' (default: a random pool)"
    )
    p.add_argument("--banner", metavar="NAME", help="set the TUI home banner to this art")
    p.add_argument("--nsfw", action="store_true", help="include 18+ pieces (NSFW mode)")


def _no_such(name, lib):
    print(f"no such art: {name}; available: {', '.join(sorted(lib))}", file=sys.stderr)
    return 1


def _show(a, title=False):
    from rich.console import Console

    console = Console()
    if title:
        console.print(f"[b]{a.name}[/b]  ({a.source})")
    for line in art.display_fit(a, console.width, None):
        console.print(line)


def _list(args, lib):
    current = art.banner_name()
    entries = [(n, lib[n]) for n in sorted(lib)]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": n,
                        "colored": a.colored,
                        "source": a.source,
                        "title": a.title,
                        "lines": len(a.lines),
                        "nsfw": a.nsfw,
                    }
                    for n, a in entries
                ]
            )
        )
        return 0
    for n, a in entries:
        user = " (user)" if a.source == "user" else ""
        tag = " [nsfw]" if a.nsfw else ""
        print(f"  {n}{user}{tag}{'  <- banner' if n == current else ''}")
    return 0


def run(args) -> int:
    nsfw = args.nsfw or None
    if args.name == "random":
        picked = art.random_pick(args.pool, nsfw=nsfw)
        if not picked:
            print("no art found", file=sys.stderr)
            return 1
        lib = art.library(nsfw=nsfw)
        _show(lib.get(picked) or next(iter(lib.values())), title=True)
        return 0
    lib = art.library(nsfw=nsfw)
    if args.banner:
        if args.banner not in lib:
            return _no_such(args.banner, lib)
        art.set_banner(args.banner)
        print(f"banner set: {args.banner}")
        return 0
    if args.name:
        if args.name not in lib:
            return _no_such(args.name, lib)
        _show(lib[args.name])
        return 0
    if not lib:
        print("no art found", file=sys.stderr)
        return 1
    return _list(args, lib)
