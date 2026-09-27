from __future__ import annotations

import json

from ... import launch
from ... import settings

NAME = "launch"


def add_parser(subparsers, common):
    subparsers.add_parser(NAME, help="which terminal --window would open", parents=[common])


def run(args) -> int:
    info = launch.describe()
    if args.json:
        print(json.dumps({**info, "command": settings.get_setting("launch_cmd")}))
        return 0
    here = f"you're in {info['in_terminal']}" if info["in_terminal"] else "couldn't tell which terminal you're in"
    print("open paws:\n")
    print("    paws               in this terminal")
    print("    paws --window      in a new terminal window\n")
    if info["would_use"]:
        print(f"--window would use: {info['would_use']}  ({here})")
        print(f"tried in this order: {', '.join(info['candidates'])}")
        print(f"command: {' '.join(info['argv'][:-1])} <script>")
    else:
        print("--window: no terminal emulator found. set PAWS_TERMINAL=<name>, e.g. PAWS_TERMINAL=kitty")
    print("\nforce one with PAWS_TERMINAL=<name>.")
    return 0
