from __future__ import annotations

import json
import sys

from ... import games
from ...textdrop import parse_text
from .add import read_list

NAME = "remove"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="remove games (appids, or --list FILE / - for stdin)", parents=[common])
    p.add_argument("appids", nargs="*")
    p.add_argument("--list", metavar="FILE", help="a text file (or - for stdin) with the ids to remove")


def run(args) -> int:
    ids = list(args.appids)
    if args.list:
        ids += parse_text(read_list(args.list)).ids
    ids = list(dict.fromkeys(ids))
    if not ids:
        print("need an appid (or --list)", file=sys.stderr)
        return 2
    if len(ids) == 1:
        result = games.apply_remove(games.plan_remove(ids[0]))
        print(json.dumps(result) if args.json else f"removed {result['removed']} thing(s)")
        return 0
    result = games.remove_bulk(ids)
    if args.json:
        print(json.dumps(result))
    else:
        missing = f", {result['not_found']} weren't there" if result["not_found"] else ""
        print(f"removed {result['removed']} thing(s) from {result['removed_games']} game(s){missing}")
    return 0
