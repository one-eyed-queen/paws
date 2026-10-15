from __future__ import annotations

import json

from ... import detect

NAME = "info"


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        NAME, help="what this machine is: os, steam, and whatever is driving it", parents=[common]
    )
    p.add_argument("--no-net", action="store_true", help="skip the github lookup so nothing waits on the network")


def run(args) -> int:
    snap = detect.snapshot()
    if args.no_net:
        # the only part that reaches out is the newest-build lookup for a linux SLSsteam install.
        # dropping it keeps this instant and honest about not having asked
        snap.backend.latest = ""
        snap.backend.update_state = ""
        snap.backend.update_why = ""

    if args.json:
        print(json.dumps(snap.as_dict(), indent=2))
        return 0
    print(snap.report())

    if snap.backend.kind and snap.backend.note and not snap.backend.installable:
        print()
        print(f"note: {snap.backend.note}")
    return 0
