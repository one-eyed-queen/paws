from __future__ import annotations

from pathlib import Path

from ...manifest import load_bundle

NAME = "drop"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="import .lua/.manifest/.key or .zip and show the plan")
    p.add_argument("files", nargs="+", type=Path)


def run(args) -> int:
    for f in args.files:
        flat = load_bundle(f).flatten()
        print(f"{f}: apps={flat['app_ids']} depots={sorted(flat['depots'])} manifests={flat['manifests']}")
    return 0
