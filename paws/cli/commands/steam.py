from __future__ import annotations

import json
import sys

from ...steam import tinker

NAME = "steam"


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        NAME, help="steam tinker: the steam client's bitness, channel, update hold and rollback", parents=[common]
    )
    sp = p.add_subparsers(dest="steam_command")
    arch = sp.add_parser("arch", parents=[common], help="which client starts: 32 (ubuntu12_32) or 64 (steamrt64)")
    arch.add_argument("bits", type=int, choices=[32, 64])
    chan = sp.add_parser("channel", parents=[common], help="stable, publicbeta, steamdeck_stable, steamdeck_publicbeta")
    chan.add_argument("branch")
    hold = sp.add_parser("hold", parents=[common], help="stop (on) or allow (off) steam updating itself")
    hold.add_argument("state", choices=["on", "off"])
    sp.add_parser("builds", parents=[common], help="older 32-bit client releases a rollback can go to")
    back = sp.add_parser("rollback", parents=[common], help="put the 32-bit client on an older release and hold it")
    back.add_argument("stamp", help="a stamp from `paws steam builds` (yyyymmdd works, the first match wins)")
    back.add_argument("--yes", action="store_true", help="don't ask")
    return p


def _status(args) -> int:
    s = tinker.state()
    if args.json:
        print(json.dumps(tinker.describe(s)))
        return 0
    print(f"steam      {s.root}")
    print(f"client     {s.version or '?'}  {s.bits}-bit" + ("" if s.can_64 else "  (no 64-bit client in this steam)"))
    print(f"channel    {s.channel_label}")
    print(f"updates    {'held' if s.held else 'on'}")
    if s.sls_bits:
        fits = "fits" if s.sls_fits else f"doesn't fit, `paws steam arch {s.sls_bits}` or a {s.bits}-bit build"
        print(f"SLSsteam   {s.sls_bits}-bit, {fits}")
    if s.forced:
        print(f"note       STEAM_FORCE_CLIENT={s.forced} is set and decides the bitness")
    if s.running:
        print("note       steam is running: close it before changing anything")
    return 0


def _rollback(args) -> int:
    builds = tinker.archived_builds()
    build = next((b for b in builds if b.stamp.startswith(args.stamp)), None)
    if build is None:
        print(f"paws: no archived release matches {args.stamp}, see `paws steam builds`", file=sys.stderr)
        return 1
    if not args.yes:
        reply = input(f"roll the steam client back to {build.date}? steam's updater runs and closes itself [y/N] ")
        if reply.strip().lower() not in ("y", "yes"):
            return 1
    result = tinker.rollback(None, build, lambda fraction, label=None: label and print(label))
    if args.json:
        print(json.dumps(result))
    elif result["ok"]:
        print(f"steam is on {result['after']} now (was {result['before']}), updates held")
    else:
        print(f"the updater finished but steam is still {result['after']} (wanted {result['target']})")
    return 0 if result["ok"] else 1


def run(args) -> int:
    action = getattr(args, "steam_command", None)
    try:
        if action == "arch":
            print(tinker.set_bits(None, args.bits))
        elif action == "channel":
            print(tinker.set_channel(None, args.branch))
        elif action == "hold":
            print(tinker.set_hold(None, args.state == "on"))
        elif action == "builds":
            builds = tinker.archived_builds()
            if args.json:
                print(json.dumps([{"stamp": b.stamp, "date": b.date} for b in builds]))
            elif not builds:
                print("the web archive didn't answer or has nothing saved, try again later")
            for b in [] if args.json else builds:
                print(f"{b.stamp}  {b.date}")
        elif action == "rollback":
            return _rollback(args)
        else:
            return _status(args)
    except tinker.TinkerError as error:
        print(f"paws: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"paws: {error}", file=sys.stderr)
        return 1
    return 0
