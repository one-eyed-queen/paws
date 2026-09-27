from __future__ import annotations

from ...config.where import find_config
from ...paths import default_config_dir
from ...util import backup

NAME = "backups"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="list the backups paws made, or restore one (config.yaml by default)")
    p.add_argument(
        "--restore",
        nargs="?",
        const="latest",
        metavar="NAME",
        help="put a backup back (default: the newest config.yaml one)",
    )


def run(args) -> int:
    files = backup.list_backups()
    if args.restore is None:
        if not files:
            print("no backups yet, paws makes one the first time it changes a file")
            return 0
        for f in files:
            tag = "  <- known-good" if f.name.endswith(".known-good") else ""
            print(f"{f.name:44} {f.stat().st_size:>8} B  {backup.age(f)}{tag}")
        return 0
    target = find_config() or default_config_dir() / "config.yaml"
    if args.restore == "latest":
        versions = backup.versions_of(target.name)
        chosen = versions[0] if versions else None
    else:
        chosen = backup.BACKUP_ROOT / args.restore
        if not chosen.is_file():
            chosen = None
    if chosen is None:
        print(f"no such backup: {args.restore}. run `paws backups` to see them")
        return 1
    target_name = chosen.name.rsplit(".", 1)[0] if "." in chosen.name else target.name
    destination = target if target_name == target.name else target.with_name(target_name)
    ok = backup.restore_backup(chosen, destination)
    print(f"restored {chosen.name} -> {destination}" if ok else "restore failed")
    return 0 if ok else 1
