from __future__ import annotations

import json

from ... import update
from ...update import git
from ...update.repo import short_name

NAME = "update"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="get the newest paws from github", parents=[common])
    p.add_argument("--check", action="store_true", help="only look, don't pull anything")


def _say(args, status):
    if args.json:
        print(
            json.dumps(
                {
                    "state": status.state,
                    "message": status.message,
                    "local": status.local,
                    "remote": status.remote,
                    "behind": status.behind,
                    "subjects": status.subjects,
                }
            )
        )
        return
    print(f"{status.state}: {status.message}  ({short_name()})")
    if status.local and status.remote and status.local != status.remote:
        print(f"  {git.short(status.local)} -> {git.short(status.remote)}")
    for line in status.subjects:
        print(f"  + {line}")


def run(args) -> int:
    status = update.check()
    if status.can_apply and not args.check:
        status = update.apply(status)
    from ...update.status import record

    record(status)
    _say(args, status)
    return 0 if status.state in ("current", "updated", "behind", "unmanaged") else 1
