from __future__ import annotations

from ... import notify

NAME = "notify"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="send a test desktop notification")
    p.add_argument("message", nargs="?", default="notifications work", help="what it says")


def run(args) -> int:
    if notify.disabled():
        print("PAWS_NO_NOTIFY is set, so nothing is sent")
        return 1
    if not notify.graphical():
        print("no desktop session (WAYLAND_DISPLAY / DISPLAY), nothing to notify")
        return 1
    tool = notify.backend()
    if tool is None:
        print("no notify-send or gdbus. install libnotify to get desktop popups")
        return 1
    ok = notify.send("paws", args.message)
    print(f"sent with {tool}" if ok else f"{tool} failed: is a notification daemon running?")
    return 0 if ok else 1
