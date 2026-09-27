from __future__ import annotations

import json

from ... import doctor as checks

NAME = "doctor"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="check steam, sls and versions", parents=[common])
    p.add_argument(
        "--reset-config", action="store_true", help="put the latest SLSsteam config in place (old one is backed up)"
    )
    p.add_argument("--clear-tickets", action="store_true", help="delete every cached ticket (copies go to the backups)")
    p.add_argument("--fix", action="store_true", help="apply safe repairs (add config keys SLSsteam expects)")


def run(args) -> int:
    from ... import repair

    if args.reset_config:
        print(repair.reset_config())
    if args.clear_tickets:
        print(repair.clear_tickets())
    if args.fix:
        fixed = checks.Doctor().fix()
        if not args.json:
            print(f"added {len(fixed)} missing config key(s): {', '.join(fixed)}" if fixed else "nothing to fix")
    d = checks.run()
    if args.json:
        print(json.dumps([{"sev": c.severity, "label": c.label, "detail": c.detail} for c in d.checks], indent=2))
    else:
        print(d.report())
    return 1 if d.fail_count else 0
