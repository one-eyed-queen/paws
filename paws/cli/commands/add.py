from __future__ import annotations

import json
import sys
from pathlib import Path

from ... import games
from ...manifest import load_bundle
from ...textdrop import parse_text

NAME = "add"


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        NAME,
        help="add games: appids, a list file (or - for stdin, e.g. pasted dlc page text), or a .lua/.manifest/.key/.zip",
        parents=[common],
    )
    p.add_argument("appids", nargs="*", help="Steam AppIds (one or many)")
    p.add_argument("--name", default="", help="name for the comment beside a single game")
    p.add_argument("--file", type=Path, help="drop a .lua/.manifest/.key/.zip to import")
    p.add_argument("--list", metavar="FILE", help="a text file (or - for stdin) with ids, links or a copied dlc page")
    p.add_argument(
        "--lookup", action="store_true", help="look names up on the store for ids that have none (needs internet)"
    )
    p.add_argument("--dry-run", action="store_true", help="show what would be added, change nothing")


def read_list(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).read_text(errors="replace")


def _bulk(args, parsed):
    if parsed.kind == "depots":
        print("that's a depot list, not apps. nothing added", file=sys.stderr)
        return 1
    if not parsed.items:
        print("no app ids found", file=sys.stderr)
        return 2
    names = games.lookup_names([i.id for i in parsed.items if not i.name]) if args.lookup else {}
    plans = games.plans_from(parsed, names)
    if args.dry_run:
        for p in plans:
            print(f"would add {p.appid}  # {p.names.get(p.appid) or p.name}")
            for a in p.additional_apps[1:]:
                print(f"would add {a}  # {p.names.get(a, '')}")
        return 0
    result = games.apply_bulk(plans)
    if args.json:
        print(json.dumps(result))
    else:
        if result["added"]:
            head = f"added {result['added']} new entr{'y' if result['added'] == 1 else 'ies'} for {result['games']} game(s)"
        elif result["errors"]:
            head = "nothing new"
        else:
            head = f"nothing new: all {result['games']} game(s) were already there"
        print(head + (f", {len(result['errors'])} error(s)" if result["errors"] else ""))
        for error in result["errors"][:10]:
            print(f"  {error}")
    return 1 if result["errors"] else 0


def run(args) -> int:
    try:
        return _run(args)
    except OSError as error:
        print(f"paws add: {error}", file=sys.stderr)
        return 1


def _fill_from_store(plan) -> None:
    """a bare `paws add 620` used to write `# 620` and no package at all, because only the store
    search paths asked for those. best-effort: offline leaves the plan exactly as it was."""
    if plan.name and plan.packages:
        return
    from ...sources.base import SourceError

    try:
        from ...sources import from_store

        info = from_store(plan.appid)
    except (ImportError, OSError, SourceError):
        return
    plan.name = plan.name or (info.name or "")
    if not plan.packages:
        plan.packages = [str(p) for p in (info.packages or [])]
    plan.names.setdefault(str(plan.appid), plan.name)


def _run(args) -> int:
    if args.file:
        plan = games.plan_from_bundle(load_bundle(args.file), name=args.name)
    elif args.list:
        return _bulk(args, parse_text(read_list(args.list)))
    elif len(args.appids) > 1 or (args.appids and not args.appids[0].isdigit()):
        return _bulk(args, parse_text("\n".join(args.appids)))
    elif args.appids:
        plan = games.plan_add(args.appids[0], name=args.name)
        _fill_from_store(plan)
    else:
        print("need an appid (or --list / --file)", file=sys.stderr)
        return 2
    if args.dry_run:
        for c in plan.changes():
            print(f"would: {c.target} {c.action} {c.detail}")
        return 0
    result = games.apply_plan(plan)
    if args.json:
        print(json.dumps({"plan": [c.__dict__ for c in plan.changes()], "result": result}))
    else:
        if result["applied"] and not result.get("added"):
            print(f"nothing new: {plan.appid} was already there")
        else:
            print(f"applied {result['applied']} change(s), {len(result['errors'])} error(s)")
        for error in result["errors"]:
            print(f"  {error}")
    return 1 if result.get("free") or result["errors"] else 0
