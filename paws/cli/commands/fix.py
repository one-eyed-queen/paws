from __future__ import annotations

import json
import sys

from ... import repair

NAME = "fix"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="find what's broken and fix it", parents=[common])
    p.add_argument("ids", nargs="*", help="only fix these (ids as printed); default: everything fixable")
    p.add_argument("--dry-run", action="store_true", help="just list what's wrong and what the fix would do")
    p.add_argument("-y", "--yes", action="store_true", help="just fix it, no questions")


def _show(problems):
    for i, p in enumerate(problems, 1):
        mark = "!!" if p.severity == "error" else "--"
        print(f"{mark} [{p.id}] {p.title}")
        print(f"     {p.detail}")
        print(f"     fix: {p.fix_note}" if p.fixable else "     (no automatic fix: see above)")


def run(args) -> int:
    problems = repair.scan(online=True)
    if args.ids:
        problems = [p for p in problems if any(p.id == i or p.id.startswith(i) for i in args.ids)]
    if args.json and args.dry_run:
        print(
            json.dumps(
                [
                    {
                        "id": p.id,
                        "title": p.title,
                        "detail": p.detail,
                        "fix": p.fix_note,
                        "fixable": p.fixable,
                        "severity": p.severity,
                    }
                    for p in problems
                ],
                indent=2,
            )
        )
        return 1 if problems else 0
    if not problems:
        print("nothing is broken")
        return 0
    if not args.json:
        _show(problems)
    if args.dry_run:
        return 1
    todo = [p for p in problems if p.fixable]
    if not todo:
        return 1
    if not args.yes:
        if not sys.stdin.isatty():
            print("run again with --yes to apply the fixes above", file=sys.stderr)
            return 1
        if input(f"fix {len(todo)} thing(s)? [y/N] ").strip().lower() not in ("y", "yes"):
            print("nothing changed")
            return 1
    failed = 0
    results = repair.apply_all(todo)
    for p, ok, message in results:
        print(f"{'fixed' if ok else 'FAILED'} [{p.id}] {message}")
        failed += not ok
    if args.json:
        print(json.dumps([{"id": p.id, "ok": ok, "result": message} for p, ok, message in results], indent=2))
    return 1 if failed else 0
