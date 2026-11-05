from __future__ import annotations

import json
import sys


NAME = "doctor"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="check steam, sls and versions", parents=[common])
    p.add_argument(
        "--reset-config", action="store_true", help="put the latest SLSsteam config in place (old one is backed up)"
    )
    p.add_argument("--clear-tickets", action="store_true", help="delete every cached ticket (copies go to the backups)")
    p.add_argument("--fix", action="store_true", help="apply safe repairs (add config keys SLSsteam expects)")


def run(args) -> int:
    from ... import doctor as checks
    from ... import repair

    if args.reset_config:
        print(repair.reset_config())
    if args.clear_tickets:
        print(repair.clear_tickets())
    if args.fix:
        fixed = checks.Doctor().fix()
        if not args.json:
            print(f"added {len(fixed)} missing config key(s): {', '.join(fixed)}" if fixed else "nothing to fix")
    if not args.json and sys.stdout.isatty():
        return _live(checks.Doctor())
    d = checks.run()
    if args.json:
        print(json.dumps([{"sev": c.severity, "label": c.label, "detail": c.detail} for c in d.checks], indent=2))
    else:
        print(d.report())
    return 1 if d.fail_count else 0


MARKS = {"ok": ("✓", "#5ff0a0"), "warn": ("!", "#ffd75f"), "error": ("✗", "#ff7a8a")}


def _live(doctor) -> int:
    """rows appear as each check finishes, nothing waits for the slowest one"""
    from rich.console import Console
    from rich.text import Text

    console = Console(highlight=False)
    width = max((len(label) for label in ("Steam client hash", "Known-good snapshot")), default=0)
    console.print(Text("paws doctor", style="bold #00d0ff"))
    with console.status("checking...", spinner="dots") as status:
        for check in doctor.stream():
            mark, colour = MARKS.get(check.severity, ("·", "#7f8db5"))
            row = Text(f" {mark} ", style=f"bold {colour}")
            row.append(f"{check.label:<{width}}", style="bold")
            row.append(f"  {check.detail}", style="#d5deff")
            console.print(row, soft_wrap=False)
            status.update(f"checking... {len(doctor.checks)} done")
    errors = doctor.fail_count
    warnings = sum(c.severity == "warn" for c in doctor.checks)
    colour = "#ff7a8a" if errors else "#ffd75f" if warnings else "#5ff0a0"
    console.print(Text(f"\n{errors} problem(s), {warnings} warning(s)", style=f"bold {colour}"))
    return 1 if errors else 0
