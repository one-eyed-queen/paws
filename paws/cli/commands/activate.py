from __future__ import annotations

import json

from ...sls import activation

NAME = "activate"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="make the tickets for an app", parents=[common])
    p.add_argument("appid")
    p.add_argument("--timeout", type=float, default=25.0)
    p.add_argument("--no-copy", action="store_true")
    p.add_argument(
        "--kind",
        choices=activation.WANTS,
        default="both",
        help="which ticket to make: both (the default), encrypted, or normal (ownership). "
        "SLSsteam only writes the encrypted ticket while the game itself runs and asks for one, "
        "so an ownership-only result means the launch never reached the game's DRM check",
    )


def run(args) -> int:
    r = activation.activate(args.appid, timeout=args.timeout, copy_to_clipboard=not args.no_copy, want=args.kind)
    missing = activation.missing_tickets(args.appid, r["tickets"], args.kind)
    if args.json:
        tickets = [
            {
                "filename": t.filename,
                "appid": t.appid,
                "encrypted": t.encrypted,
                "steam_id": t.steam_id,
                "size": t.size,
                "path": str(t.path) if t.path else None,
            }
            for t in r["tickets"]
        ]
        print(json.dumps({"method": r["method"], "tickets": tickets, "missing": missing, "error": r["error"]}))
    else:
        got = ", ".join(f"'{t.filename}'" for t in r["tickets"]) or "-"
        print(f"method={r['method']} tickets=[{got}] copied={r['copied']} error={r['error']}")
        if missing:
            print(f"note: these never landed: {', '.join(missing)}")
            if "encryptedTicket_" + args.appid + ".yaml" in missing:
                print(
                    "  the encrypted ticket is only written while the game itself is running and requests one. "
                    "if this game uses one, launch it once through SLSsteam (paws has it in the config already) "
                    "and the file will show up here"
                )
    primary = "encrypted" if args.kind != "normal" else "normal"
    have = {"encrypted" if t.encrypted else "normal" for t in r["tickets"]}
    if not have:
        return 1
    return 0 if primary in have else 2
