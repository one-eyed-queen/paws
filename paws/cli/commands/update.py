from __future__ import annotations

import json

from ... import update
from ...update import git
from ...update.repo import short_name
from ...update.status import Status, force, record

NAME = "update"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="get the newest paws from github", parents=[common])
    p.add_argument("--check", action="store_true", help="only look, don't pull anything")
    p.add_argument(
        "--force",
        action="store_true",
        help="update anyway: stash local changes and reset onto the remote tip, even if git "
        "would normally stop. works the same from any shell and on any os",
    )
    p.add_argument(
        "--no-stash",
        action="store_true",
        help="with --force, discard local changes instead of putting them somewhere you can get them back",
    )


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
    if args.force:
        if args.check:
            _say(args, Status("current", "--force and --check don't go together"))
            return 2
        status = force(keep_changes=not args.no_stash)
        record(status)
        _say(args, status)
        return 0 if status.state in ("updated", "current") else 1

    status = update.check()
    if status.can_apply and not args.check:
        status = update.apply(status)
    record(status)
    _say(args, status)
    # "unmanaged" (not a git checkout) and "blocked" (local changes, or diverged history) both
    # mean paws did not update. they used to exit 0, so scripts and `set -e` saw a clean run
    # that had in fact changed nothing
    if status.state in ("current", "updated"):
        return 0
    if status.state == "behind" and args.check:
        return 0  # --check only reports, so "there are updates pending" isn't a failure
    return 1
