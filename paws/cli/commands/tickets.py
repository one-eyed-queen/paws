from __future__ import annotations

import getpass
import json
import sys

from ...sls import encode, tickets
from ...util import clipboard

NAME = "tickets"


def add_parser(subparsers, common):
    p = subparsers.add_parser(NAME, help="list cached tickets", parents=[common])
    sp = p.add_subparsers(dest="tickets_command")

    pack = sp.add_parser("pack", parents=[common], help="pack both tickets of an app into one paw1e string")
    pack.add_argument("appid", help="pack whatever cache files exist for this app (encrypted + normal)")
    pack.add_argument("--no-copy", action="store_true", help="don't put the string on the clipboard, just print it")
    pack.add_argument(
        "--passphrase-file", metavar="FILE", help="read the passphrase from the first line of FILE ('-' = stdin)"
    )

    unpack = sp.add_parser("unpack", parents=[common], help="unpack a paw1e string back into the ticket cache")
    unpack.add_argument("data", help="the paw1e.<base85> encrypted string")
    unpack.add_argument(
        "--passphrase-file", metavar="FILE", help="read the passphrase from the first line of FILE ('-' = stdin)"
    )

    show = sp.add_parser("show", parents=[common], help="show both tickets of an app side by side")
    show.add_argument("appid")
    return p


def _ask_passphrase(confirm, pfile=None):
    if pfile is not None:
        if pfile == "-":
            pw = sys.stdin.readline().rstrip("\r\n")
        else:
            with open(pfile, encoding="utf-8") as fh:
                pw = fh.readline().rstrip("\r\n")
        if not pw:
            raise ValueError("passphrase file was empty")
        return pw
    pw = getpass.getpass("passphrase for this backup: ")
    if confirm:
        again = getpass.getpass("repeat it: ")
        if pw != again:
            raise ValueError("passphrases don't match")
    if not pw:
        raise ValueError("passphrase can't be empty")
    return pw


def run(args) -> int:
    subparsers = getattr(args, "tickets_command", None)
    if subparsers == "pack":
        try:
            pw = _ask_passphrase(confirm=True, pfile=getattr(args, "passphrase_file", None))
            s = encode.pack_tickets(args.appid, pw)
        except (ValueError, OSError) as e:
            print(f"paws: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({"appid": args.appid, "paw1e": s}))
            return 0
        if args.no_copy or not clipboard.copy(s):
            print(s)
        else:
            print(f"packed {args.appid} to the clipboard as a paw1e string ({len(s)} chars; keep the passphrase!)")
        return 0

    if subparsers == "unpack":
        try:
            pw = _ask_passphrase(confirm=False, pfile=getattr(args, "passphrase_file", None))
            saved = encode.restore(args.data, pw)
        except (ValueError, OSError) as e:
            print(f"paws: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps([{"filename": t.filename, "appid": t.appid} for t in saved]))
        else:
            print(f"restored {len(saved)} ticket(s): " + ", ".join(t.filename for t in saved))
        return 0

    if subparsers == "show":
        try:
            text = encode.detail_text(args.appid)
        except ValueError as e:
            print(f"paws: {e}", file=sys.stderr)
            return 1
        print(text)
        return 0

    for t in tickets.list_tickets():
        print(t.filename, t.steam_id, t.payload[:24])
    return 0
