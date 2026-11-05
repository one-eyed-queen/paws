from __future__ import annotations

import sys
from pathlib import Path

from ... import drop
from ...manifest import load_bundle

NAME = "drop"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="add a game from .lua/.manifest/.key files or a .zip/.rar/.7z")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--dry-run", action="store_true", help="show what's in the files, change nothing")


def run(args) -> int:
    gone = [f for f in args.files if not f.exists()]
    if gone:
        for f in gone:
            print(f"paws: no such file: {f}", file=sys.stderr)
        return 1
    if args.dry_run:
        for f in args.files:
            flat = load_bundle(f).flatten()
            print(f"{f}: apps={flat['app_ids']} depots={sorted(flat['depots'])} manifests={flat['manifests']}")
        return 0
    result = drop.import_any(args.files)
    print(result.title)
    for line in result.lines:
        if line:
            print(f"  {line}")
    return 0 if result.ok else 1
