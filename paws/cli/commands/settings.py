from __future__ import annotations

import json

from ... import settings

NAME = "settings"
_ON = ("on", "1", "yes", "true")


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="paws settings, nsfw and the feature switches", parents=[common])
    p.add_argument(
        "what",
        nargs="?",
        choices=[
            "nsfw",
            "random",
            "sound",
            "icons",
            "type",
            "notifications",
            "terminal",
            "features",
            "launch",
            "update",
        ],
        default="nsfw",
        help="show or set",
    )
    p.add_argument(
        "value",
        nargs="?",
        help="on/off for nsfw, random, update; riced or minimal for type; a terminal name (or auto) for terminal; the command for launch",
    )


def run(args) -> int:
    what = args.what or "nsfw"
    if what == "nsfw":
        if args.value is not None:
            settings.set_setting("nsfw", args.value.lower() in _ON)
        report = settings.status_report()
        print(json.dumps(report) if args.json else f"nsfw mode: {'on' if report['nsfw'] else 'off'}")
    elif what == "random":
        if args.value is not None:
            settings.set_setting("random_banner", args.value.lower() in _ON)
        print(f"random banner: {'on' if settings.status_report()['random_banner'] else 'off'}")
    elif what == "sound":
        if args.value is not None:
            settings.set_setting("notify_sound", args.value.lower() in _ON)
        print(f"notification sound: {'on' if settings.get_setting('notify_sound') else 'off'}")
    elif what == "notifications":
        if args.value is not None:
            v = args.value.lower()
            settings.set_setting(
                "notifications",
                v if v in ("auto", "always", "toasts", "off") else ("off" if v in ("no", "0") else "auto"),
            )
        print(f"notifications: {settings.get_setting('notifications')} (auto / always / toasts / off)")
    elif what == "icons":
        if args.value is not None:
            settings.set_setting("icons", args.value if args.value in ("auto", "nerd", "plain", "none") else "auto")
        print(f"icons: {settings.get_setting('icons')} (auto / nerd / plain / none; takes effect next start)")
    elif what == "type":
        if args.value is not None:
            from ... import riced

            wanted = args.value if args.value in settings.TYPES else "riced"
            if wanted == "riced" and not riced.installed():
                print("riced isn't installed (no pictures, art or games here). run ./scripts/install.sh --riced")
            else:
                settings.set_setting("type", wanted)
        print(f"type: {settings.ui_type()} (riced / minimal; applies right away)")
    elif what == "terminal":
        if args.value is not None:
            settings.set_setting("terminal", args.value)
        print(f"terminal: {settings.get_setting('terminal')}")
    elif what == "features":
        report = settings.status_report()
        if args.json:
            print(json.dumps(report["features"]))
        else:
            for f in settings.FEATURES:
                print(f"{'on' if report['features'][f] else 'off (struck-out)':18} {f}")
    elif what == "update":
        if args.value is not None:
            settings.set_setting("auto_update", args.value.lower() in _ON)
        print(f"update on start: {'on' if settings.get_setting('auto_update') else 'off'}")
    elif what == "launch":
        if args.value is not None:
            settings.set_setting("launch_cmd", args.value)
        print(f"launch command: {settings.get_setting('launch_cmd')}")
    return 0
